from fastapi import FastAPI, APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, date, timedelta
import duckdb
import nflreadpy as nfl
import pandas as pd
import asyncio
from concurrent.futures import ThreadPoolExecutor
import traceback
import requests
import json
import time
from bs4 import BeautifulSoup
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import re

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Create the main app without a prefix
app = FastAPI(title="Fantasy Football Database API", version="1.0.0")

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Initialize DuckDB connection
db_path = ROOT_DIR / "fantasy_football.db"
conn = duckdb.connect(str(db_path))

# Thread pool for async operations
executor = ThreadPoolExecutor(max_workers=3)

# DraftKings PPR Scoring System
DRAFTKINGS_SCORING = {
    'passing_yards': 0.04,  # 1 point per 25 yards (0.04 per yard)
    'passing_tds': 4,
    'interceptions': -1,
    'rushing_yards': 0.1,  # 1 point per 10 yards
    'rushing_tds': 6,
    'receptions': 1,  # PPR - 1 point per reception
    'receiving_yards': 0.1,  # 1 point per 10 yards
    'receiving_tds': 6,
    'fumbles_lost': -1,
    '2pt_conversions': 2
}

# LA Team Mapping - Fix for nflreadpy data ambiguity
# Maps (opponent_team, week, season) to correct LA team (LAR = Rams, LAC = Chargers)
LA_TEAM_MAPPING = {
    # 2025 Season mappings based on NFL schedule
    ('TEN', 2, 2025): 'LAC',  # Titans vs Chargers Week 2
    ('PHI', 3, 2025): 'LAR',  # Eagles vs Rams Week 3  
    ('IND', 4, 2025): 'LAC',  # Colts vs Chargers Week 4
    ('SF', 5, 2025): 'LAR',   # 49ers vs Rams Week 5
    # Add more mappings as needed
}

def resolve_la_team(opponent_team, week, season):
    """Resolve ambiguous 'LA' opponent to specific team (LAR or LAC)"""
    if opponent_team != 'LA':
        return opponent_team
    
    # Look up the correct LA team based on opponent and week
    mapping_key = (opponent_team if opponent_team != 'LA' else None, week, season)
    
    # Since we have opponent as 'LA', we need to reverse lookup
    # Find which team plays in this week/season combination
    for (opp, wk, ssn), la_team in LA_TEAM_MAPPING.items():
        if wk == week and ssn == season:
            # This is a potential match, but we need more context
            # For now, return the mapped team
            return la_team
    
    # Fallback: if no mapping found, return LAR (Rams) as default
    # This can be improved with more comprehensive schedule data
    return 'LAR'

# All NFL Teams
NFL_TEAMS = {
    'ARI': 'Arizona Cardinals',
    'ATL': 'Atlanta Falcons',
    'BAL': 'Baltimore Ravens', 
    'BUF': 'Buffalo Bills',
    'CAR': 'Carolina Panthers',
    'CHI': 'Chicago Bears',
    'CIN': 'Cincinnati Bengals',
    'CLE': 'Cleveland Browns',
    'DAL': 'Dallas Cowboys',
    'DEN': 'Denver Broncos',
    'DET': 'Detroit Lions',
    'GB': 'Green Bay Packers',
    'HOU': 'Houston Texans',
    'IND': 'Indianapolis Colts',
    'JAX': 'Jacksonville Jaguars',
    'KC': 'Kansas City Chiefs',
    'LV': 'Las Vegas Raiders',
    'LAC': 'Los Angeles Chargers',
    'LAR': 'Los Angeles Rams',
    'MIA': 'Miami Dolphins',
    'MIN': 'Minnesota Vikings',
    'NE': 'New England Patriots',
    'NO': 'New Orleans Saints',
    'NYG': 'New York Giants',
    'NYJ': 'New York Jets',
    'PHI': 'Philadelphia Eagles',
    'PIT': 'Pittsburgh Steelers',
    'SF': 'San Francisco 49ers',
    'SEA': 'Seattle Seahawks',
    'TB': 'Tampa Bay Buccaneers',
    'TEN': 'Tennessee Titans',
    'WAS': 'Washington Commanders'
}

# RapidAPI configuration for DraftKings pricing
RAPIDAPI_KEY = "31cd7fd5cfmsh0039d0aaa4b3cf4p187526jsn4273673a1752"
RAPIDAPI_HOST = "tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"

# Skill positions to track for snap counts
SKILL_POSITIONS = ['QB', 'RB', 'WR', 'TE']

# Models
class PlayerStats(BaseModel):
    player_id: str
    player_name: str
    position: str
    team: str
    season: int
    week: Optional[int] = None
    opponent: Optional[str] = None
    passing_yards: Optional[float] = 0
    passing_tds: Optional[int] = 0
    interceptions: Optional[int] = 0
    rushing_yards: Optional[float] = 0
    rushing_tds: Optional[int] = 0
    receptions: Optional[int] = 0
    receiving_yards: Optional[float] = 0
    receiving_tds: Optional[int] = 0
    fumbles_lost: Optional[int] = 0
    fantasy_points: Optional[float] = 0
    snap_percentage: Optional[float] = None
    snap_count: Optional[int] = None
    targets: Optional[int] = 0
    dk_salary: Optional[int] = None

class RefreshResponse(BaseModel):
    success: bool
    message: str
    records_loaded: int
    timestamp: datetime
    snap_records_loaded: Optional[int] = 0

class DraftKingsResponse(BaseModel):
    success: bool
    data: Optional[Dict] = None
    message: str
    timestamp: datetime
    records_processed: Optional[int] = 0

class SnapCountsResponse(BaseModel):
    success: bool
    data: Optional[Dict] = None
    message: str
    timestamp: datetime
    records_loaded: Optional[int] = 0

def normalize_player_name(name: str) -> str:
    """
    Normalize player names for better matching between data sources.
    Handles common variations like Jr/Sr suffixes, punctuation, etc.
    """
    if not name:
        return ""
    
    # Convert to lowercase and strip whitespace
    normalized = name.lower().strip()
    
    # Remove common suffixes that vary between sources
    suffixes = [' jr.', ' jr', ' sr.', ' sr', ' iii', ' ii', ' iv']
    for suffix in suffixes:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)].strip()
            break
    
    # Remove periods and extra spaces
    normalized = normalized.replace('.', '').replace('  ', ' ')
    
    return normalized

def calculate_fantasy_points(stats: Dict) -> float:
    """Calculate DraftKings PPR fantasy points"""
    points = 0
    
    # Passing
    if stats.get('passing_yards'):
        points += stats['passing_yards'] * DRAFTKINGS_SCORING['passing_yards']
    if stats.get('passing_tds'):
        points += stats['passing_tds'] * DRAFTKINGS_SCORING['passing_tds']
    if stats.get('interceptions'):
        points += stats['interceptions'] * DRAFTKINGS_SCORING['interceptions']
    
    # Rushing
    if stats.get('rushing_yards'):
        points += stats['rushing_yards'] * DRAFTKINGS_SCORING['rushing_yards']
    if stats.get('rushing_tds'):
        points += stats['rushing_tds'] * DRAFTKINGS_SCORING['rushing_tds']
    
    # Receiving
    if stats.get('receptions'):
        points += stats['receptions'] * DRAFTKINGS_SCORING['receptions']
    if stats.get('receiving_yards'):
        points += stats['receiving_yards'] * DRAFTKINGS_SCORING['receiving_yards']
    if stats.get('receiving_tds'):
        points += stats['receiving_tds'] * DRAFTKINGS_SCORING['receiving_tds']
    
    # Fumbles
    if stats.get('fumbles_lost'):
        points += stats['fumbles_lost'] * DRAFTKINGS_SCORING['fumbles_lost']
    
    return round(points, 2)

def fetch_draftkings_salaries(season: int, week: int) -> Dict:
    """Fetch DraftKings salaries from RapidAPI for specific season/week"""
    url = f"https://{RAPIDAPI_HOST}/getDFSsalaries"
    
    querystring = {
        "week": str(week),
        "season": str(season),
        "site": "draftkings"
    }
    
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": RAPIDAPI_HOST,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, params=querystring, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        logging.info(f"DraftKings API response received for season {season}, week {week}")
        
        processed_data = []
        if 'body' in data and 'draftkings' in data['body']:
            for player in data['body']['draftkings']:
                # Filter for offensive positions only
                position = player.get('pos', '').upper()
                if position in SKILL_POSITIONS:
                    # Parse salary (handle both string and numeric)
                    salary_raw = player.get('salary', 0)
                    if isinstance(salary_raw, str):
                        salary = int(salary_raw.replace('$', '').replace(',', '')) if salary_raw else 0
                    else:
                        salary = int(salary_raw) if salary_raw else 0
                    
                    processed_data.append({
                        'player_name': player.get('longName', ''),
                        'team': player.get('team', '').upper(),
                        'position': position,
                        'salary': salary,
                        'dk_player_id': player.get('playerID', ''),
                        'season': season,
                        'week': week
                    })
        
        return {
            'success': True,
            'data': processed_data,
            'count': len(processed_data)
        }
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Error fetching DraftKings salaries for {season} week {week}: {e}")
        return {
            'success': False,
            'error': str(e),
            'data': []
        }
    except Exception as e:
        logging.error(f"Unexpected error in DraftKings API for {season} week {week}: {e}")
        return {
            'success': False,
            'error': str(e),
            'data': []
        }

def load_snap_counts_for_seasons(seasons: List[int]) -> Dict:
    """Load snap counts for specified seasons using nflreadpy"""
    try:
        total_loaded = 0
        
        for season in seasons:
            logging.info(f"Loading snap counts for season {season}")
            
            try:
                # Load snap counts using nflreadpy
                snap_counts_data = nfl.load_snap_counts(seasons=[season])
                
                if snap_counts_data is not None and len(snap_counts_data) > 0:
                    # Convert Polars to Pandas
                    snap_counts_pd = snap_counts_data.to_pandas()
                    
                    # Filter for skill positions and regular season games
                    if 'game_type' in snap_counts_pd.columns:
                        snap_counts_pd = snap_counts_pd[snap_counts_pd['game_type'] == 'REG']
                        logging.info(f"After filtering for regular season: {len(snap_counts_pd)} records")
                    
                    # Filter for skill positions only
                    snap_counts_pd = snap_counts_pd[snap_counts_pd['position'].isin(SKILL_POSITIONS)]
                    logging.info(f"After filtering for skill positions: {len(snap_counts_pd)} records")
                    
                    # Filter for players with offensive snaps (ensure column exists and has data)
                    if 'offense_snaps' in snap_counts_pd.columns:
                        snap_counts_pd = snap_counts_pd[snap_counts_pd['offense_snaps'] > 0]
                        logging.info(f"After filtering for offense_snaps > 0: {len(snap_counts_pd)} records")
                    else:
                        logging.warning("No 'offense_snaps' column found in data")
                    
                    if len(snap_counts_pd) > 0:
                        # Create unique ID for each record - use simpler approach
                        snap_counts_pd['id'] = snap_counts_pd.apply(
                            lambda row: f"{row.get('season', '')}_{row.get('week', '')}_{row.get('team', '')}_{row.get('player', '').replace(' ', '_')}", axis=1
                        )
                        
                        # Delete existing data for this season
                        conn.execute("DELETE FROM snap_counts WHERE season = ?", [season])
                        
                        # Register DataFrame with DuckDB
                        conn.register('snap_counts_df', snap_counts_pd)
                        
                        # Insert snap counts data
                        conn.execute("""
                            INSERT INTO snap_counts 
                            SELECT 
                                id,
                                COALESCE(pfr_player_id, '') as player_id,
                                player as player_name,
                                team,
                                season,
                                week,
                                COALESCE(offense_snaps, 0) as offense_snaps,
                                COALESCE(offense_pct, 0.0) as offense_pct,
                                COALESCE(defense_snaps, 0) as defense_snaps,
                                COALESCE(defense_pct, 0.0) as defense_pct,
                                COALESCE(st_snaps, 0) as st_snaps,
                                COALESCE(st_pct, 0.0) as st_pct,
                                position,
                                COALESCE(pfr_game_id, game_id, '') as game_id,
                                COALESCE(opponent, '') as opponent_team,
                                CURRENT_TIMESTAMP as created_at
                            FROM snap_counts_df
                        """)
                        
                        snap_count = len(snap_counts_pd)
                        total_loaded += snap_count
                        logging.info(f"Loaded {snap_count} snap count records for season {season}")
                    else:
                        logging.warning(f"No skill position snap counts found for season {season}")
                else:
                    logging.warning(f"No snap counts data returned for season {season}")
                    
            except Exception as e:
                logging.error(f"Error loading snap counts for season {season}: {e}")
                logging.error(traceback.format_exc())
                continue
        
        return {
            'success': True,
            'total_loaded': total_loaded
        }
        
    except Exception as e:
        logging.error(f"Error in load_snap_counts_for_seasons: {e}")
        logging.error(traceback.format_exc())
        return {
            'success': False,
            'error': str(e),
            'total_loaded': 0
        }

def is_pricing_cached(season: int, week: int) -> bool:
    """Check if pricing data is already cached for a specific season/week"""
    try:
        result = conn.execute(
            "SELECT COUNT(*) FROM draftkings_pricing WHERE season = ? AND week = ?",
            [season, week]
        ).fetchone()
        return result[0] > 0
    except Exception as e:
        logging.error(f"Error checking pricing cache: {e}")
        return False

def cache_draftkings_pricing(pricing_data: List[Dict], season: int, week: int) -> int:
    """Cache DraftKings pricing data to database"""
    try:
        # Delete existing data for this season/week
        conn.execute(
            "DELETE FROM draftkings_pricing WHERE season = ? AND week = ?",
            [season, week]
        )
        
        # Insert new data
        cached_count = 0
        for player in pricing_data:
            try:
                conn.execute("""
                    INSERT INTO draftkings_pricing 
                    (player_name, team, position, season, week, salary, dk_player_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    player['player_name'],
                    player['team'],
                    player['position'],
                    player['season'],
                    player['week'],
                    player['salary'],
                    player['dk_player_id'],
                    datetime.now(timezone.utc)
                ])
                cached_count += 1
            except Exception as e:
                logging.error(f"Error inserting pricing data for {player['player_name']}: {e}")
                continue
        
        logging.info(f"Cached {cached_count} DraftKings pricing records for season {season}, week {week}")
        return cached_count
        
    except Exception as e:
        logging.error(f"Error caching DraftKings pricing: {e}")
        return 0

def load_historical_draftkings_data(start_season: int = 2024, end_season: int = 2025) -> Dict:
    """Load historical DraftKings data for all weeks from start_season to current"""
    total_cached = 0
    total_weeks_processed = 0
    errors = []
    
    current_date = datetime.now()
    current_season = current_date.year if current_date.month >= 9 else current_date.year - 1
    
    for season in range(start_season, end_season + 1):
        # Determine max week for each season
        if season < current_season:
            max_week = 18  # Full season for past years
        elif season == current_season:
            # For current season, estimate current week (rough calculation)
            if current_date.month >= 9:  # Season started
                weeks_since_start = (current_date - datetime(season, 9, 1)).days // 7
                max_week = min(max(weeks_since_start, 1), 18)
            else:
                max_week = 1
        else:
            continue  # Future seasons
        
        for week in range(1, max_week + 1):
            # Skip if already cached (unless it's current week of current season)
            if season == current_season and week == max_week:
                # Always refresh current week
                pass
            elif is_pricing_cached(season, week):
                logging.info(f"Skipping cached data for season {season}, week {week}")
                continue
            
            try:
                logging.info(f"Fetching DraftKings data for season {season}, week {week}")
                result = fetch_draftkings_salaries(season, week)
                
                if result['success'] and result['data']:
                    cached = cache_draftkings_pricing(result['data'], season, week)
                    total_cached += cached
                    logging.info(f"Successfully cached {cached} records for season {season}, week {week}")
                else:
                    error_msg = f"No data for season {season}, week {week}: {result.get('error', 'Unknown error')}"
                    errors.append(error_msg)
                    logging.warning(error_msg)
                
                total_weeks_processed += 1
                
                # Rate limiting - wait between requests
                time.sleep(1)
                
            except Exception as e:
                error_msg = f"Error processing season {season}, week {week}: {str(e)}"
                errors.append(error_msg)
                logging.error(error_msg)
                continue
    
    return {
        'total_cached': total_cached,
        'weeks_processed': total_weeks_processed,
        'errors': errors
    }

async def load_draftkings_pricing_from_sheets():
    """Load DraftKings pricing data from Google Sheets for weeks 4 and 5"""
    try:
        # DraftKings pricing data from Google Sheets
        pricing_data = [
            # Week 4 data
            {"week": 4, "name": "Christian McCaffrey", "team": "SF", "pos": "RB", "salary": 8500},
            {"week": 4, "name": "Josh Allen", "team": "BUF", "pos": "QB", "salary": 7700},
            {"week": 4, "name": "Lamar Jackson", "team": "BAL", "pos": "QB", "salary": 7500},
            {"week": 4, "name": "Puka Nacua", "team": "LAR", "pos": "WR", "salary": 7900},
            {"week": 4, "name": "Jalen Hurts", "team": "PHI", "pos": "QB", "salary": 6700},
            {"week": 4, "name": "De'Von Achane", "team": "MIA", "pos": "RB", "salary": 7000},
            {"week": 4, "name": "Jonathan Taylor", "team": "IND", "pos": "RB", "salary": 7500},
            {"week": 4, "name": "Bijan Robinson", "team": "ATL", "pos": "RB", "salary": 8200},
            {"week": 4, "name": "Justin Herbert", "team": "LAC", "pos": "QB", "salary": 6300},
            {"week": 4, "name": "Jahmyr Gibbs", "team": "DET", "pos": "RB", "salary": 7700},
            {"week": 4, "name": "Drake Maye", "team": "NE", "pos": "QB", "salary": 5500},
            {"week": 4, "name": "Brock Purdy", "team": "SF", "pos": "QB", "salary": 6100},
            {"week": 4, "name": "Patrick Mahomes", "team": "KC", "pos": "QB", "salary": 6000},
            {"week": 4, "name": "Caleb Williams", "team": "CHI", "pos": "QB", "salary": 5800},
            {"week": 4, "name": "Daniel Jones", "team": "IND", "pos": "QB", "salary": 5600},
            {"week": 4, "name": "Bo Nix", "team": "DEN", "pos": "QB", "salary": 5600},
            {"week": 4, "name": "Marcus Mariota", "team": "WAS", "pos": "QB", "salary": 5000},
            {"week": 4, "name": "Justin Fields", "team": "NYJ", "pos": "QB", "salary": 5300},
            {"week": 4, "name": "Baker Mayfield", "team": "TB", "pos": "QB", "salary": 6500},
            {"week": 4, "name": "Jordan Love", "team": "GB", "pos": "QB", "salary": 6200},
            {"week": 4, "name": "Amon-Ra St. Brown", "team": "DET", "pos": "WR", "salary": 7300},
            {"week": 4, "name": "Jared Goff", "team": "DET", "pos": "QB", "salary": 6400},
            {"week": 4, "name": "Josh Jacobs", "team": "GB", "pos": "RB", "salary": 6800},
            {"week": 4, "name": "Bucky Irving", "team": "TB", "pos": "RB", "salary": 6900},
            {"week": 4, "name": "Saquon Barkley", "team": "PHI", "pos": "RB", "salary": 7600},
            {"week": 4, "name": "Kyler Murray", "team": "ARI", "pos": "QB", "salary": 5800},
            {"week": 4, "name": "James Cook", "team": "BUF", "pos": "RB", "salary": 7100},
            {"week": 4, "name": "Geno Smith", "team": "LV", "pos": "QB", "salary": 5400},
            {"week": 4, "name": "Nico Collins", "team": "HOU", "pos": "WR", "salary": 7400},
            {"week": 4, "name": "Jaxon Smith-Njigba", "team": "SEA", "pos": "WR", "salary": 6600},
            {"week": 4, "name": "Ja'Marr Chase", "team": "CIN", "pos": "WR", "salary": 8000},
            {"week": 4, "name": "Justin Jefferson", "team": "MIN", "pos": "WR", "salary": 7500},
            {"week": 4, "name": "Malik Nabers", "team": "NYG", "pos": "WR", "salary": 7000},
            {"week": 4, "name": "Davante Adams", "team": "LAR", "pos": "WR", "salary": 6200},
            {"week": 4, "name": "Cam Skattebo", "team": "NYG", "pos": "RB", "salary": 5500},
            {"week": 4, "name": "Matthew Stafford", "team": "LAR", "pos": "QB", "salary": 5900},
            {"week": 4, "name": "Trevor Lawrence", "team": "JAX", "pos": "QB", "salary": 5200},
            {"week": 4, "name": "Dak Prescott", "team": "DAL", "pos": "QB", "salary": 5700},
            {"week": 4, "name": "C.J. Stroud", "team": "HOU", "pos": "QB", "salary": 5300},
            {"week": 4, "name": "Derrick Henry", "team": "BAL", "pos": "RB", "salary": 7200},
            {"week": 4, "name": "Jaxson Dart", "team": "NYG", "pos": "QB", "salary": 4500},
            {"week": 4, "name": "Omarion Hampton", "team": "LAC", "pos": "RB", "salary": 5900},
            {"week": 4, "name": "Sam Darnold", "team": "SEA", "pos": "QB", "salary": 5000},
            {"week": 4, "name": "Kyren Williams", "team": "LAR", "pos": "RB", "salary": 6300},
            {"week": 4, "name": "Bryce Young", "team": "CAR", "pos": "QB", "salary": 4900},
            {"week": 4, "name": "Jordan Mason", "team": "MIN", "pos": "RB", "salary": 6400},
            {"week": 4, "name": "Carson Wentz", "team": "MIN", "pos": "QB", "salary": 5100},
            {"week": 4, "name": "Tua Tagovailoa", "team": "MIA", "pos": "QB", "salary": 5200},
            {"week": 4, "name": "Michael Penix Jr.", "team": "ATL", "pos": "QB", "salary": 5100},
            {"week": 4, "name": "Tyreek Hill", "team": "MIA", "pos": "WR", "salary": 6500},
            {"week": 4, "name": "Trey McBride", "team": "ARI", "pos": "TE", "salary": 5600},
            {"week": 4, "name": "Courtland Sutton", "team": "DEN", "pos": "WR", "salary": 6100},
            {"week": 4, "name": "A.J. Brown", "team": "PHI", "pos": "WR", "salary": 6400},
            {"week": 4, "name": "Alvin Kamara", "team": "NO", "pos": "RB", "salary": 6100},
            {"week": 4, "name": "Garrett Wilson", "team": "NYJ", "pos": "WR", "salary": 6200},
            {"week": 4, "name": "Jake Browning", "team": "CIN", "pos": "QB", "salary": 5400},
            {"week": 4, "name": "J.K. Dobbins", "team": "DEN", "pos": "RB", "salary": 5800},
            {"week": 4, "name": "Breece Hall", "team": "NYJ", "pos": "RB", "salary": 5700},
            {"week": 4, "name": "George Pickens", "team": "DAL", "pos": "WR", "salary": 6300},
            {"week": 4, "name": "Brock Bowers", "team": "LV", "pos": "TE", "salary": 5800},
            {"week": 4, "name": "Ladd McConkey", "team": "LAC", "pos": "WR", "salary": 6500},
            {"week": 4, "name": "Spencer Rattler", "team": "NO", "pos": "QB", "salary": 4700},
            {"week": 4, "name": "Trey Benson", "team": "ARI", "pos": "RB", "salary": 5500},
            {"week": 4, "name": "Drake London", "team": "ATL", "pos": "WR", "salary": 5700},
            {"week": 4, "name": "Chuba Hubbard", "team": "CAR", "pos": "RB", "salary": 6000},
            {"week": 4, "name": "Ricky Pearsall", "team": "SF", "pos": "WR", "salary": 5700},
            {"week": 4, "name": "Javonte Williams", "team": "DAL", "pos": "RB", "salary": 5900},
            {"week": 4, "name": "Emeka Egbuka", "team": "TB", "pos": "WR", "salary": 6800},
            {"week": 4, "name": "Joe Flacco", "team": "CLE", "pos": "QB", "salary": 4700},
            {"week": 4, "name": "Quinshon Judkins", "team": "CLE", "pos": "RB", "salary": 5500},
            {"week": 4, "name": "Cameron Ward", "team": "TEN", "pos": "QB", "salary": 4800},
            {"week": 4, "name": "Jakobi Meyers", "team": "LV", "pos": "WR", "salary": 5400},
            {"week": 4, "name": "Chase Brown", "team": "CIN", "pos": "RB", "salary": 6600},
            {"week": 4, "name": "Aaron Rodgers", "team": "PIT", "pos": "QB", "salary": 5300},
            {"week": 4, "name": "Tony Pollard", "team": "TEN", "pos": "RB", "salary": 5600},
            {"week": 4, "name": "Keenan Allen", "team": "LAC", "pos": "WR", "salary": 5300},
            {"week": 4, "name": "Kenneth Walker III", "team": "SEA", "pos": "RB", "salary": 6500},
            {"week": 4, "name": "Rome Odunze", "team": "CHI", "pos": "WR", "salary": 6300},
            {"week": 4, "name": "Ashton Jeanty", "team": "LV", "pos": "RB", "salary": 6200},
            {"week": 4, "name": "Michael Pittman Jr.", "team": "IND", "pos": "WR", "salary": 5100},
            {"week": 4, "name": "Kenneth Gainwell", "team": "PIT", "pos": "RB", "salary": 4400},
            {"week": 4, "name": "DeVonta Smith", "team": "PHI", "pos": "WR", "salary": 5400},
            {"week": 4, "name": "D'Andre Swift", "team": "CHI", "pos": "RB", "salary": 5400},
            {"week": 4, "name": "Brian Thomas Jr.", "team": "JAX", "pos": "WR", "salary": 6100},
            {"week": 4, "name": "DJ Moore", "team": "CHI", "pos": "WR", "salary": 5600},
            {"week": 4, "name": "Tetairoa McMillan", "team": "CAR", "pos": "WR", "salary": 5900},
            {"week": 4, "name": "Zay Flowers", "team": "BAL", "pos": "WR", "salary": 6700},
            {"week": 4, "name": "Deebo Samuel Sr.", "team": "WAS", "pos": "WR", "salary": 6000},
            {"week": 4, "name": "Travis Etienne Jr.", "team": "JAX", "pos": "RB", "salary": 5800},
            {"week": 4, "name": "Tyler Warren", "team": "IND", "pos": "TE", "salary": 4600},
            {"week": 4, "name": "David Montgomery", "team": "DET", "pos": "RB", "salary": 5700},
            {"week": 4, "name": "Jaylen Waddle", "team": "MIA", "pos": "WR", "salary": 5500},
            {"week": 4, "name": "Chris Olave", "team": "NO", "pos": "WR", "salary": 5100},
            {"week": 4, "name": "Jerry Jeudy", "team": "CLE", "pos": "WR", "salary": 4900},
            {"week": 4, "name": "Tee Higgins", "team": "CIN", "pos": "WR", "salary": 5800},
            {"week": 4, "name": "Tucker Kraft", "team": "GB", "pos": "TE", "salary": 4700},
            {"week": 4, "name": "Nick Chubb", "team": "HOU", "pos": "RB", "salary": 5100},
            {"week": 4, "name": "Xavier Worthy", "team": "KC", "pos": "WR", "salary": 5800},
            {"week": 4, "name": "Marvin Harrison Jr.", "team": "ARI", "pos": "WR", "salary": 5300},
            {"week": 4, "name": "Jameson Williams", "team": "DET", "pos": "WR", "salary": 5900},
            {"week": 4, "name": "DK Metcalf", "team": "PIT", "pos": "WR", "salary": 5400},
            {"week": 4, "name": "Jake Ferguson", "team": "DAL", "pos": "TE", "salary": 4300},
            {"week": 4, "name": "Quentin Johnston", "team": "LAC", "pos": "WR", "salary": 5500},
            {"week": 4, "name": "Sam LaPorta", "team": "DET", "pos": "TE", "salary": 4400},
            {"week": 4, "name": "Juwan Johnson", "team": "NO", "pos": "TE", "salary": 4200},
            {"week": 4, "name": "Jauan Jennings", "team": "SF", "pos": "WR", "salary": 5000},
            {"week": 4, "name": "Travis Kelce", "team": "KC", "pos": "TE", "salary": 4800},
            {"week": 4, "name": "Jordan Addison", "team": "MIN", "pos": "WR", "salary": 5000},
            {"week": 4, "name": "Hunter Henry", "team": "NE", "pos": "TE", "salary": 4000},
            {"week": 4, "name": "Khalil Shakir", "team": "BUF", "pos": "WR", "salary": 5300},
            {"week": 4, "name": "Keon Coleman", "team": "BUF", "pos": "WR", "salary": 5600},
            {"week": 4, "name": "Wan'Dale Robinson", "team": "NYG", "pos": "WR", "salary": 5000},
            {"week": 4, "name": "Cooper Kupp", "team": "SEA", "pos": "WR", "salary": 4700},
            {"week": 4, "name": "Romeo Doubs", "team": "GB", "pos": "WR", "salary": 4500},
            {"week": 4, "name": "Zach Ertz", "team": "WAS", "pos": "TE", "salary": 4100},
            {"week": 4, "name": "Darnell Mooney", "team": "ATL", "pos": "WR", "salary": 4700},
            {"week": 4, "name": "David Njoku", "team": "CLE", "pos": "TE", "salary": 3800},
            {"week": 4, "name": "Matthew Golden", "team": "GB", "pos": "WR", "salary": 5200},
            {"week": 4, "name": "TreVeyon Henderson", "team": "NE", "pos": "RB", "salary": 5200},
            {"week": 4, "name": "Cedric Tillman", "team": "CLE", "pos": "WR", "salary": 4200},
            {"week": 4, "name": "Rhamondre Stevenson", "team": "NE", "pos": "RB", "salary": 5100},
            {"week": 4, "name": "Calvin Ridley", "team": "TEN", "pos": "WR", "salary": 4900},
            {"week": 4, "name": "Rashid Shaheed", "team": "NO", "pos": "WR", "salary": 4600},
            {"week": 4, "name": "T.J. Hockenson", "team": "MIN", "pos": "TE", "salary": 3900},
            {"week": 4, "name": "Dalton Kincaid", "team": "BUF", "pos": "TE", "salary": 4500},
            {"week": 4, "name": "Stefon Diggs", "team": "NE", "pos": "WR", "salary": 4500},
            {"week": 4, "name": "Christian Kirk", "team": "HOU", "pos": "WR", "salary": 4400},
            {"week": 4, "name": "Zach Charbonnet", "team": "SEA", "pos": "RB", "salary": 4800},
            {"week": 4, "name": "Josh Downs", "team": "IND", "pos": "WR", "salary": 4100},
            {"week": 4, "name": "Mark Andrews", "team": "BAL", "pos": "TE", "salary": 4300},
            {"week": 4, "name": "Tyquan Thornton", "team": "KC", "pos": "WR", "salary": 4000},
            {"week": 4, "name": "Calvin Austin III", "team": "PIT", "pos": "WR", "salary": 4200},
            {"week": 4, "name": "Tre Tucker", "team": "LV", "pos": "WR", "salary": 4200},
            {"week": 4, "name": "Marquise Brown", "team": "KC", "pos": "WR", "salary": 5200},
            {"week": 4, "name": "Dallas Goedert", "team": "PHI", "pos": "TE", "salary": 3900},
            {"week": 4, "name": "Harold Fannin Jr.", "team": "CLE", "pos": "TE", "salary": 3700},
            {"week": 4, "name": "Jacory Croskey-Merritt", "team": "WAS", "pos": "RB", "salary": 5300},
            {"week": 4, "name": "Kyle Pitts Sr.", "team": "ATL", "pos": "TE", "salary": 3600},
            {"week": 4, "name": "Chris Rodriguez Jr.", "team": "WAS", "pos": "RB", "salary": 4200},
            {"week": 4, "name": "Kareem Hunt", "team": "KC", "pos": "RB", "salary": 4800},
            {"week": 4, "name": "Brenton Strange", "team": "JAX", "pos": "TE", "salary": 3200},
            {"week": 4, "name": "Travis Hunter", "team": "JAX", "pos": "WR", "salary": 4600},
            {"week": 4, "name": "Rashod Bateman", "team": "BAL", "pos": "WR", "salary": 4800},
            {"week": 4, "name": "Isiah Pacheco", "team": "KC", "pos": "RB", "salary": 5000},
            {"week": 4, "name": "Chig Okonkwo", "team": "TEN", "pos": "TE", "salary": 3500},
            {"week": 4, "name": "Tory Horton", "team": "SEA", "pos": "WR", "salary": 3700},
            {"week": 4, "name": "Dalton Schultz", "team": "HOU", "pos": "TE", "salary": 3300},
            {"week": 4, "name": "Elic Ayomanor", "team": "TEN", "pos": "WR", "salary": 3900},
            {"week": 4, "name": "Joshua Palmer", "team": "BUF", "pos": "WR", "salary": 4300},
            {"week": 4, "name": "Chris Godwin", "team": "TB", "pos": "WR", "salary": 6000},
            {"week": 4, "name": "DeMario Douglas", "team": "NE", "pos": "WR", "salary": 3800},
            {"week": 4, "name": "Kayshon Boutte", "team": "NE", "pos": "WR", "salary": 4300},
            {"week": 4, "name": "Jeremy McNichols", "team": "WAS", "pos": "RB", "salary": 4900},
            {"week": 4, "name": "Jonnu Smith", "team": "PIT", "pos": "TE", "salary": 3300},
            {"week": 4, "name": "Evan Engram", "team": "DEN", "pos": "TE", "salary": 3700},
            {"week": 4, "name": "RJ Harvey", "team": "DEN", "pos": "RB", "salary": 4800},
            {"week": 4, "name": "Hunter Renfrow", "team": "CAR", "pos": "WR", "salary": 3800},
            {"week": 4, "name": "KaVontae Turpin", "team": "DAL", "pos": "WR", "salary": 3800},
            {"week": 4, "name": "Marvin Mims Jr.", "team": "DEN", "pos": "WR", "salary": 3700},
            {"week": 4, "name": "Luke McCaffrey", "team": "WAS", "pos": "WR", "salary": 3400},
            {"week": 4, "name": "Woody Marks", "team": "HOU", "pos": "RB", "salary": 4400},
            {"week": 4, "name": "Rico Dowdle", "team": "CAR", "pos": "RB", "salary": 4500},
            {"week": 4, "name": "Bhayshul Tuten", "team": "JAX", "pos": "RB", "salary": 4800},
            {"week": 4, "name": "Michael Wilson", "team": "ARI", "pos": "WR", "salary": 3300},
            {"week": 4, "name": "Dontayvion Wicks", "team": "GB", "pos": "WR", "salary": 4000},
            {"week": 4, "name": "Rachaad White", "team": "TB", "pos": "RB", "salary": 4900},
            {"week": 4, "name": "Luther Burden III", "team": "CHI", "pos": "WR", "salary": 4700},
            {"week": 4, "name": "Cade Otton", "team": "TB", "pos": "TE", "salary": 3400},
            {"week": 4, "name": "Adam Thielen", "team": "MIN", "pos": "WR", "salary": 4000},
            {"week": 4, "name": "Cole Kmet", "team": "CHI", "pos": "TE", "salary": 3000},
            {"week": 4, "name": "Pat Freiermuth", "team": "PIT", "pos": "TE", "salary": 2800},
            {"week": 4, "name": "Ray-Ray McCloud III", "team": "ATL", "pos": "WR", "salary": 3700},
            {"week": 4, "name": "Ollie Gordon II", "team": "MIA", "pos": "RB", "salary": 4500},
            {"week": 4, "name": "Demarcus Robinson", "team": "SF", "pos": "WR", "salary": 3500},
            {"week": 4, "name": "Sterling Shepard", "team": "TB", "pos": "WR", "salary": 4000},
            {"week": 4, "name": "Jayden Higgins", "team": "HOU", "pos": "WR", "salary": 3900},
            {"week": 4, "name": "Malik Washington", "team": "MIA", "pos": "WR", "salary": 3500},
            {"week": 4, "name": "Miles Sanders", "team": "DAL", "pos": "RB", "salary": 4400},
            {"week": 4, "name": "Tyler Allgeier", "team": "ATL", "pos": "RB", "salary": 4700},
            {"week": 4, "name": "Emari Demercado", "team": "ARI", "pos": "RB", "salary": 4300},
            {"week": 4, "name": "Jalen Tolbert", "team": "DAL", "pos": "WR", "salary": 3300},
            {"week": 4, "name": "Devin Singletary", "team": "NYG", "pos": "RB", "salary": 4500},
            {"week": 4, "name": "Jerome Ford", "team": "CLE", "pos": "RB", "salary": 4600},
            {"week": 4, "name": "Dont'e Thornton Jr.", "team": "LV", "pos": "WR", "salary": 3900},
            {"week": 4, "name": "Kendrick Bourne", "team": "SF", "pos": "WR", "salary": 3700},
            {"week": 4, "name": "Brandin Cooks", "team": "NO", "pos": "WR", "salary": 3600},
            {"week": 4, "name": "Jalen Nailor", "team": "MIN", "pos": "WR", "salary": 3500},
            {"week": 4, "name": "Jake Tonges", "team": "SF", "pos": "TE", "salary": 3100},
            {"week": 4, "name": "Antonio Gibson", "team": "NE", "pos": "RB", "salary": 4600},
            {"week": 4, "name": "Kaleb Johnson", "team": "PIT", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Ray Davis", "team": "BUF", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Isaiah Likely", "team": "BAL", "pos": "TE", "salary": 3300},
            {"week": 4, "name": "Justice Hill", "team": "BAL", "pos": "RB", "salary": 4700},
            {"week": 4, "name": "Zavier Scott", "team": "MIN", "pos": "RB", "salary": 4200},
            {"week": 4, "name": "Mason Taylor", "team": "NYJ", "pos": "TE", "salary": 2700},
            {"week": 4, "name": "Hassan Haskins", "team": "LAC", "pos": "RB", "salary": 4400},
            {"week": 4, "name": "Mike Gesicki", "team": "CIN", "pos": "TE", "salary": 2900},
            {"week": 4, "name": "JuJu Smith-Schuster", "team": "KC", "pos": "WR", "salary": 3800},
            {"week": 4, "name": "Darius Slayton", "team": "NYG", "pos": "WR", "salary": 3700},
            {"week": 4, "name": "Theo Johnson", "team": "NYG", "pos": "TE", "salary": 2900},
            {"week": 4, "name": "Olamide Zaccheaus", "team": "CHI", "pos": "WR", "salary": 3600},
            {"week": 4, "name": "Brian Robinson Jr.", "team": "SF", "pos": "RB", "salary": 4500},
            {"week": 4, "name": "Tyler Higbee", "team": "LAR", "pos": "TE", "salary": 2800},
            {"week": 4, "name": "Parker Washington", "team": "JAX", "pos": "WR", "salary": 3700},
            {"week": 4, "name": "Tommy Tremble", "team": "CAR", "pos": "TE", "salary": 2700},
            {"week": 4, "name": "Malik Heath", "team": "GB", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Josh Reynolds", "team": "NYJ", "pos": "WR", "salary": 3500},
            {"week": 4, "name": "Andrei Iosivas", "team": "CIN", "pos": "WR", "salary": 3100},
            {"week": 4, "name": "Dylan Sampson", "team": "CLE", "pos": "RB", "salary": 4200},
            {"week": 4, "name": "Mack Hollins", "team": "NE", "pos": "WR", "salary": 3300},
            {"week": 4, "name": "AJ Barner", "team": "SEA", "pos": "TE", "salary": 2800},
            {"week": 4, "name": "DeAndre Hopkins", "team": "BAL", "pos": "WR", "salary": 4500},
            {"week": 4, "name": "Oronde Gadsden", "team": "LAC", "pos": "TE", "salary": 2600},
            {"week": 4, "name": "Kyle Monangai", "team": "CHI", "pos": "RB", "salary": 4400},
            {"week": 4, "name": "Kyle Williams", "team": "NE", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Tyler Lockett", "team": "TEN", "pos": "WR", "salary": 3500},
            {"week": 4, "name": "Jordan Whittington", "team": "LAR", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Ty Johnson", "team": "BUF", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Darren Waller", "team": "MIA", "pos": "TE", "salary": 3500},
            {"week": 4, "name": "Kendre Miller", "team": "NO", "pos": "RB", "salary": 4100},
            {"week": 4, "name": "Blake Corum", "team": "LAR", "pos": "RB", "salary": 4300},
            {"week": 4, "name": "Samaje Perine", "team": "CIN", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Elijah Moore", "team": "BUF", "pos": "WR", "salary": 3600},
            {"week": 4, "name": "Tre' Harris", "team": "LAC", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Chris Brooks", "team": "GB", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Austin Hooper", "team": "NE", "pos": "TE", "salary": 3000},
            {"week": 4, "name": "Braelon Allen", "team": "NYJ", "pos": "RB", "salary": 5200},
            {"week": 4, "name": "Brycen Tremayne", "team": "CAR", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Noah Gray", "team": "KC", "pos": "TE", "salary": 2700},
            {"week": 4, "name": "Jaylin Noel", "team": "HOU", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Xavier Hutchinson", "team": "HOU", "pos": "WR", "salary": 3400},
            {"week": 4, "name": "Jahan Dotson", "team": "PHI", "pos": "WR", "salary": 3400},
            {"week": 4, "name": "Nick Westbrook-Ikhine", "team": "MIA", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Jaylin Lane", "team": "WAS", "pos": "WR", "salary": 3300},
            {"week": 4, "name": "Elijah Arroyo", "team": "SEA", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Greg Dortch", "team": "ARI", "pos": "WR", "salary": 3200},
            {"week": 4, "name": "Gunnar Helm", "team": "TEN", "pos": "TE", "salary": 2600},
            {"week": 4, "name": "Tyler Conklin", "team": "LAC", "pos": "TE", "salary": 2700},
            {"week": 4, "name": "LeQuint Allen Jr.", "team": "JAX", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Isaac TeSlaa", "team": "DET", "pos": "WR", "salary": 3500},
            {"week": 4, "name": "Adam Trautman", "team": "DEN", "pos": "TE", "salary": 2600},
            {"week": 4, "name": "Jamari Thrash", "team": "CLE", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Jack Bech", "team": "LV", "pos": "WR", "salary": 3600},
            {"week": 4, "name": "Dareke Young", "team": "SEA", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Trey Sermon", "team": "PIT", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "David Moore", "team": "CAR", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Emanuel Wilson", "team": "GB", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Julius Chestnut", "team": "TEN", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Chimere Dike", "team": "TEN", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Kalif Raymond", "team": "DET", "pos": "WR", "salary": 3200},
            {"week": 4, "name": "Luke Farrell", "team": "SF", "pos": "TE", "salary": 3000},
            {"week": 4, "name": "Dawson Knox", "team": "BUF", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Luke Musgrave", "team": "GB", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Roman Wilson", "team": "PIT", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Jake Bobo", "team": "SEA", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Savion Williams", "team": "GB", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Ben Sinnott", "team": "WAS", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Davis Allen", "team": "LAR", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Ben Skowronek", "team": "PIT", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Devontez Walker", "team": "BAL", "pos": "WR", "salary": 3400},
            {"week": 4, "name": "Pat Bryant", "team": "DEN", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Josh Oliver", "team": "MIN", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Tylan Wallace", "team": "BAL", "pos": "WR", "salary": 3200},
            {"week": 4, "name": "Tahj Brooks", "team": "CIN", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Mitchell Tinsley", "team": "CIN", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Mitchell Evans", "team": "CAR", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Luke Schoonmaker", "team": "DAL", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Elijah Higgins", "team": "ARI", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Kyle Juszczyk", "team": "SF", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Tutu Atwell", "team": "LAR", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Jeremy Ruckert", "team": "NYJ", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Tez Johnson", "team": "TB", "pos": "WR", "salary": 3200},
            {"week": 4, "name": "Drew Sample", "team": "CIN", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Isaiah Davis", "team": "NYJ", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Devaughn Vele", "team": "NO", "pos": "WR", "salary": 3100},
            {"week": 4, "name": "Brock Wright", "team": "DET", "pos": "TE", "salary": 2900},
            {"week": 4, "name": "Will Shipley", "team": "PHI", "pos": "RB", "salary": 4300},
            {"week": 4, "name": "Dominic Lovett", "team": "DET", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Brashard Smith", "team": "KC", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Drew Ogletree", "team": "IND", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Jalen Royals", "team": "KC", "pos": "WR", "salary": 3300},
            {"week": 4, "name": "Allen Lazard", "team": "NYJ", "pos": "WR", "salary": 3200},
            {"week": 4, "name": "Colby Parkinson", "team": "LAR", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Ryan Miller", "team": "TB", "pos": "WR", "salary": 3100},
            {"week": 4, "name": "Curtis Samuel", "team": "BUF", "pos": "WR", "salary": 3200},
            {"week": 4, "name": "Johnny Mundt", "team": "JAX", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Jamal Agnew", "team": "ATL", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Tyler Badie", "team": "DEN", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Hunter Long", "team": "JAX", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "LaJohntay Wester", "team": "BAL", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "DJ Giddens", "team": "IND", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Tanner Conner", "team": "MIA", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Chris Moore", "team": "WAS", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Cam Grandy", "team": "CIN", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Kameron Johnson", "team": "TB", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Eric Saubert", "team": "SEA", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Trent Sherfield Sr.", "team": "DEN", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Tip Reiman", "team": "ARI", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "A.J. Dillon", "team": "PHI", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Brevyn Spann-Ford", "team": "DAL", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Payne Durham", "team": "TB", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Isaiah Bond", "team": "CLE", "pos": "WR", "salary": 3100},
            {"week": 4, "name": "Ian Thomas", "team": "LV", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Alec Ingold", "team": "MIA", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Casey Washington", "team": "ATL", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Scotty Miller", "team": "PIT", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Dylan Laube", "team": "LV", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Nate Adkins", "team": "DEN", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Andrew Beck", "team": "NYJ", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Blake Whiteheart", "team": "CLE", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Dillon Gabriel", "team": "CLE", "pos": "QB", "salary": 4200},
            {"week": 4, "name": "Daniel Bellinger", "team": "NYG", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Jack Stoll", "team": "NO", "pos": "TE", "salary": 2600},
            {"week": 4, "name": "Nikko Remigio", "team": "KC", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Roschon Johnson", "team": "CHI", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "John FitzPatrick", "team": "GB", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Van Jefferson", "team": "TEN", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Connor Heyward", "team": "PIT", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Arian Smith", "team": "NYJ", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Ben Sims", "team": "GB", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Keandre Lambert-Smith", "team": "LAC", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Jalen Milroe", "team": "SEA", "pos": "QB", "salary": 4000},
            {"week": 4, "name": "Dare Ogunbowale", "team": "HOU", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Grant Calcaterra", "team": "PHI", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Skyy Moore", "team": "SF", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Darnell Washington", "team": "PIT", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "Jalin Hyatt", "team": "NYG", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "James Mitchell", "team": "CAR", "pos": "TE", "salary": 2500},
            {"week": 4, "name": "John Metchie III", "team": "PHI", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Anthony Gould", "team": "IND", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Xavier Weaver", "team": "ARI", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Jaylen Wright", "team": "MIA", "pos": "RB", "salary": 4000},
            {"week": 4, "name": "Tai Felton", "team": "MIN", "pos": "WR", "salary": 3000},
            {"week": 4, "name": "Charlie Jones", "team": "CIN", "pos": "WR", "salary": 3000},
            
            # Week 5 data
            {"week": 5, "name": "Christian McCaffrey", "team": "SF", "pos": "RB", "salary": 8600},
            {"week": 5, "name": "Josh Allen", "team": "BUF", "pos": "QB", "salary": 8000},
            {"week": 5, "name": "De'Von Achane", "team": "MIA", "pos": "RB", "salary": 7300},
            {"week": 5, "name": "Puka Nacua", "team": "LAR", "pos": "WR", "salary": 8400},
            {"week": 5, "name": "Justin Fields", "team": "NYJ", "pos": "QB", "salary": 5600},
            {"week": 5, "name": "Jalen Hurts", "team": "PHI", "pos": "QB", "salary": 6800},
            {"week": 5, "name": "Justin Herbert", "team": "LAC", "pos": "QB", "salary": 6100},
            {"week": 5, "name": "Patrick Mahomes", "team": "KC", "pos": "QB", "salary": 6600},
            {"week": 5, "name": "Kyler Murray", "team": "ARI", "pos": "QB", "salary": 5900},
            {"week": 5, "name": "Jayden Daniels", "team": "WAS", "pos": "QB", "salary": 7000},
            {"week": 5, "name": "Jahmyr Gibbs", "team": "DET", "pos": "RB", "salary": 7700},
            {"week": 5, "name": "Jonathan Taylor", "team": "IND", "pos": "RB", "salary": 8000},
            {"week": 5, "name": "Daniel Jones", "team": "IND", "pos": "QB", "salary": 5800},
            {"week": 5, "name": "Amon-Ra St. Brown", "team": "DET", "pos": "WR", "salary": 7900},
            {"week": 5, "name": "Omarion Hampton", "team": "LAC", "pos": "RB", "salary": 6500},
            {"week": 5, "name": "Drake Maye", "team": "NE", "pos": "QB", "salary": 6000},
            {"week": 5, "name": "Jared Goff", "team": "DET", "pos": "QB", "salary": 6500},
            {"week": 5, "name": "Baker Mayfield", "team": "TB", "pos": "QB", "salary": 6300},
            {"week": 5, "name": "Jaxson Dart", "team": "NYG", "pos": "QB", "salary": 5300},
            {"week": 5, "name": "Dak Prescott", "team": "DAL", "pos": "QB", "salary": 6000},
            {"week": 5, "name": "James Cook", "team": "BUF", "pos": "RB", "salary": 7400},
            {"week": 5, "name": "Bo Nix", "team": "DEN", "pos": "QB", "salary": 5700},
            {"week": 5, "name": "Cam Skattebo", "team": "NYG", "pos": "RB", "salary": 6000},
            {"week": 5, "name": "Jaxon Smith-Njigba", "team": "SEA", "pos": "WR", "salary": 7100},
            {"week": 5, "name": "Saquon Barkley", "team": "PHI", "pos": "RB", "salary": 7500},
            {"week": 5, "name": "Derrick Henry", "team": "BAL", "pos": "RB", "salary": 7000},
            {"week": 5, "name": "George Pickens", "team": "DAL", "pos": "WR", "salary": 6600},
            {"week": 5, "name": "Garrett Wilson", "team": "NYJ", "pos": "WR", "salary": 6100},
            {"week": 5, "name": "Tua Tagovailoa", "team": "MIA", "pos": "QB", "salary": 5500},
            {"week": 5, "name": "Ja'Marr Chase", "team": "CIN", "pos": "WR", "salary": 7800},
            {"week": 5, "name": "Geno Smith", "team": "LV", "pos": "QB", "salary": 5400},
            {"week": 5, "name": "Breece Hall", "team": "NYJ", "pos": "RB", "salary": 5600},
            {"week": 5, "name": "Bryce Young", "team": "CAR", "pos": "QB", "salary": 4700},
            {"week": 5, "name": "Trevor Lawrence", "team": "JAX", "pos": "QB", "salary": 5100},
            {"week": 5, "name": "Javonte Williams", "team": "DAL", "pos": "RB", "salary": 6200},
            {"week": 5, "name": "Sam Darnold", "team": "SEA", "pos": "QB", "salary": 5100},
            {"week": 5, "name": "Matthew Stafford", "team": "LAR", "pos": "QB", "salary": 6400},
            {"week": 5, "name": "Nico Collins", "team": "HOU", "pos": "WR", "salary": 6800},
            {"week": 5, "name": "C.J. Stroud", "team": "HOU", "pos": "QB", "salary": 5200},
            {"week": 5, "name": "Ashton Jeanty", "team": "LV", "pos": "RB", "salary": 6700},
            {"week": 5, "name": "Spencer Rattler", "team": "NO", "pos": "QB", "salary": 4800},
            {"week": 5, "name": "Justin Jefferson", "team": "MIN", "pos": "WR", "salary": 7300},
            {"week": 5, "name": "Jakobi Meyers", "team": "LV", "pos": "WR", "salary": 5600},
            {"week": 5, "name": "Quinshon Judkins", "team": "CLE", "pos": "RB", "salary": 5800},
            {"week": 5, "name": "Jake Browning", "team": "CIN", "pos": "QB", "salary": 4900},
            {"week": 5, "name": "Alvin Kamara", "team": "NO", "pos": "RB", "salary": 5900},
            {"week": 5, "name": "Carson Wentz", "team": "MIN", "pos": "QB", "salary": 5000},
            {"week": 5, "name": "Trey McBride", "team": "ARI", "pos": "TE", "salary": 5800},
            {"week": 5, "name": "Rachaad White", "team": "TB", "pos": "RB", "salary": 4700},
            {"week": 5, "name": "Davante Adams", "team": "LAR", "pos": "WR", "salary": 6200},
            {"week": 5, "name": "Chase Brown", "team": "CIN", "pos": "RB", "salary": 6100},
            {"week": 5, "name": "Quentin Johnston", "team": "LAC", "pos": "WR", "salary": 5700},
            {"week": 5, "name": "Mac Jones", "team": "SF", "pos": "QB", "salary": 4700},
            {"week": 5, "name": "Jordan Mason", "team": "MIN", "pos": "RB", "salary": 6400},
            {"week": 5, "name": "Emeka Egbuka", "team": "TB", "pos": "WR", "salary": 6900},
            {"week": 5, "name": "Kyren Williams", "team": "LAR", "pos": "RB", "salary": 6000},
            {"week": 5, "name": "Dillon Gabriel", "team": "CLE", "pos": "QB", "salary": 4000},
            {"week": 5, "name": "Michael Pittman Jr.", "team": "IND", "pos": "WR", "salary": 5100},
            {"week": 5, "name": "Tetairoa McMillan", "team": "CAR", "pos": "WR", "salary": 5700},
            {"week": 5, "name": "Jaylen Waddle", "team": "MIA", "pos": "WR", "salary": 5400},
            {"week": 5, "name": "Keenan Allen", "team": "LAC", "pos": "WR", "salary": 5600},
            {"week": 5, "name": "Deebo Samuel Sr.", "team": "WAS", "pos": "WR", "salary": 6300},
            {"week": 5, "name": "Rico Dowdle", "team": "CAR", "pos": "RB", "salary": 4300},
            {"week": 5, "name": "Travis Etienne Jr.", "team": "JAX", "pos": "RB", "salary": 5900},
            {"week": 5, "name": "Ladd McConkey", "team": "LAC", "pos": "WR", "salary": 5500},
            {"week": 5, "name": "A.J. Brown", "team": "PHI", "pos": "WR", "salary": 6000},
            {"week": 5, "name": "Xavier Worthy", "team": "KC", "pos": "WR", "salary": 5800},
            {"week": 5, "name": "Marvin Harrison Jr.", "team": "ARI", "pos": "WR", "salary": 5400},
            {"week": 5, "name": "Brian Thomas Jr.", "team": "JAX", "pos": "WR", "salary": 6100},
            {"week": 5, "name": "Cameron Ward", "team": "TEN", "pos": "QB", "salary": 4600},
            {"week": 5, "name": "Jake Ferguson", "team": "DAL", "pos": "TE", "salary": 4800},
            {"week": 5, "name": "Courtland Sutton", "team": "DEN", "pos": "WR", "salary": 6000},
            {"week": 5, "name": "Tyler Warren", "team": "IND", "pos": "TE", "salary": 4700},
            {"week": 5, "name": "Kenneth Walker III", "team": "SEA", "pos": "RB", "salary": 6300},
            {"week": 5, "name": "Zay Flowers", "team": "BAL", "pos": "WR", "salary": 6200},
            {"week": 5, "name": "David Montgomery", "team": "DET", "pos": "RB", "salary": 5200},
            {"week": 5, "name": "J.K. Dobbins", "team": "DEN", "pos": "RB", "salary": 5500},
            {"week": 5, "name": "Jameson Williams", "team": "DET", "pos": "WR", "salary": 4900},
            {"week": 5, "name": "Chris Olave", "team": "NO", "pos": "WR", "salary": 5200},
            {"week": 5, "name": "Chris Godwin", "team": "TB", "pos": "WR", "salary": 5900},
            {"week": 5, "name": "Cooper Rush", "team": "BAL", "pos": "QB", "salary": 4300},
            {"week": 5, "name": "DeVonta Smith", "team": "PHI", "pos": "WR", "salary": 5000},
            {"week": 5, "name": "Wan'Dale Robinson", "team": "NYG", "pos": "WR", "salary": 5300},
            {"week": 5, "name": "Woody Marks", "team": "HOU", "pos": "RB", "salary": 5400},
            {"week": 5, "name": "Tee Higgins", "team": "CIN", "pos": "WR", "salary": 5900},
            {"week": 5, "name": "Sam LaPorta", "team": "DET", "pos": "TE", "salary": 4200},
            {"week": 5, "name": "Stefon Diggs", "team": "NE", "pos": "WR", "salary": 4800},
            {"week": 5, "name": "Tony Pollard", "team": "TEN", "pos": "RB", "salary": 5400},
            {"week": 5, "name": "Khalil Shakir", "team": "BUF", "pos": "WR", "salary": 5200},
            {"week": 5, "name": "Jerry Jeudy", "team": "CLE", "pos": "WR", "salary": 4700},
            {"week": 5, "name": "Hunter Henry", "team": "NE", "pos": "TE", "salary": 4500},
            {"week": 5, "name": "Travis Kelce", "team": "KC", "pos": "TE", "salary": 4300},
            {"week": 5, "name": "Calvin Ridley", "team": "TEN", "pos": "WR", "salary": 4800},
            {"week": 5, "name": "Cooper Kupp", "team": "SEA", "pos": "WR", "salary": 4600},
            {"week": 5, "name": "Emari Demercado", "team": "ARI", "pos": "RB", "salary": 4700},
            {"week": 5, "name": "Tre Tucker", "team": "LV", "pos": "WR", "salary": 4700},
            {"week": 5, "name": "Jordan Addison", "team": "MIN", "pos": "WR", "salary": 5300},
            {"week": 5, "name": "Juwan Johnson", "team": "NO", "pos": "TE", "salary": 3900},
            {"week": 5, "name": "Keon Coleman", "team": "BUF", "pos": "WR", "salary": 5100},
            {"week": 5, "name": "Rashid Shaheed", "team": "NO", "pos": "WR", "salary": 4500},
            {"week": 5, "name": "Jacory Croskey-Merritt", "team": "WAS", "pos": "RB", "salary": 5100},
            {"week": 5, "name": "TreVeyon Henderson", "team": "NE", "pos": "RB", "salary": 5300},
            {"week": 5, "name": "Rhamondre Stevenson", "team": "NE", "pos": "RB", "salary": 4800},
            {"week": 5, "name": "RJ Harvey", "team": "DEN", "pos": "RB", "salary": 4500},
            {"week": 5, "name": "Zach Charbonnet", "team": "SEA", "pos": "RB", "salary": 5300},
            {"week": 5, "name": "Dalton Kincaid", "team": "BUF", "pos": "TE", "salary": 4400},
            {"week": 5, "name": "Michael Carter", "team": "ARI", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Zach Ertz", "team": "WAS", "pos": "TE", "salary": 3800},
            {"week": 5, "name": "Dallas Goedert", "team": "PHI", "pos": "TE", "salary": 4100},
            {"week": 5, "name": "Brenton Strange", "team": "JAX", "pos": "TE", "salary": 3600},
            {"week": 5, "name": "Troy Franklin", "team": "DEN", "pos": "WR", "salary": 4000},
            {"week": 5, "name": "Kendrick Bourne", "team": "SF", "pos": "WR", "salary": 3500},
            {"week": 5, "name": "Josh Downs", "team": "IND", "pos": "WR", "salary": 4100},
            {"week": 5, "name": "Malik Washington", "team": "MIA", "pos": "WR", "salary": 3900},
            {"week": 5, "name": "Elic Ayomanor", "team": "TEN", "pos": "WR", "salary": 4100},
            {"week": 5, "name": "Darren Waller", "team": "MIA", "pos": "TE", "salary": 3500},
            {"week": 5, "name": "Darius Slayton", "team": "NYG", "pos": "WR", "salary": 4300},
            {"week": 5, "name": "Marquise Brown", "team": "KC", "pos": "WR", "salary": 5000},
            {"week": 5, "name": "Isiah Pacheco", "team": "KC", "pos": "RB", "salary": 5200},
            {"week": 5, "name": "T.J. Hockenson", "team": "MIN", "pos": "TE", "salary": 3800},
            {"week": 5, "name": "Kareem Hunt", "team": "KC", "pos": "RB", "salary": 4700},
            {"week": 5, "name": "Harold Fannin Jr.", "team": "CLE", "pos": "TE", "salary": 3400},
            {"week": 5, "name": "Nick Chubb", "team": "HOU", "pos": "RB", "salary": 5200},
            {"week": 5, "name": "David Njoku", "team": "CLE", "pos": "TE", "salary": 3500},
            {"week": 5, "name": "Demarcus Robinson", "team": "SF", "pos": "WR", "salary": 3300},
            {"week": 5, "name": "Dalton Schultz", "team": "HOU", "pos": "TE", "salary": 3600},
            {"week": 5, "name": "Christian Kirk", "team": "HOU", "pos": "WR", "salary": 4300},
            {"week": 5, "name": "Luke McCaffrey", "team": "WAS", "pos": "WR", "salary": 3700},
            {"week": 5, "name": "Travis Hunter", "team": "JAX", "pos": "WR", "salary": 4600},
            {"week": 5, "name": "Mark Andrews", "team": "BAL", "pos": "TE", "salary": 4000},
            {"week": 5, "name": "Jalen Tolbert", "team": "DAL", "pos": "WR", "salary": 3600},
            {"week": 5, "name": "Joshua Palmer", "team": "BUF", "pos": "WR", "salary": 3800},
            {"week": 5, "name": "Chris Rodriguez Jr.", "team": "WAS", "pos": "RB", "salary": 4100},
            {"week": 5, "name": "Chig Okonkwo", "team": "TEN", "pos": "TE", "salary": 3300},
            {"week": 5, "name": "Mason Taylor", "team": "NYJ", "pos": "TE", "salary": 2800},
            {"week": 5, "name": "Kayshon Boutte", "team": "NE", "pos": "WR", "salary": 4000},
            {"week": 5, "name": "Tory Horton", "team": "SEA", "pos": "WR", "salary": 3600},
            {"week": 5, "name": "Isaiah Bond", "team": "CLE", "pos": "WR", "salary": 3200},
            {"week": 5, "name": "Jake Tonges", "team": "SF", "pos": "TE", "salary": 3200},
            {"week": 5, "name": "Dont'e Thornton Jr.", "team": "LV", "pos": "WR", "salary": 3700},
            {"week": 5, "name": "Michael Wilson", "team": "ARI", "pos": "WR", "salary": 3300},
            {"week": 5, "name": "Theo Johnson", "team": "NYG", "pos": "TE", "salary": 3400},
            {"week": 5, "name": "Tyjae Spears", "team": "TEN", "pos": "RB", "salary": 4400},
            {"week": 5, "name": "Marvin Mims Jr.", "team": "DEN", "pos": "WR", "salary": 3800},
            {"week": 5, "name": "Jeremy McNichols", "team": "WAS", "pos": "RB", "salary": 4600},
            {"week": 5, "name": "Hunter Renfrow", "team": "CAR", "pos": "WR", "salary": 3700},
            {"week": 5, "name": "JuJu Smith-Schuster", "team": "KC", "pos": "WR", "salary": 3900},
            {"week": 5, "name": "Sterling Shepard", "team": "TB", "pos": "WR", "salary": 3900},
            {"week": 5, "name": "Tommy Tremble", "team": "CAR", "pos": "TE", "salary": 2900},
            {"week": 5, "name": "Sean Tucker", "team": "TB", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Evan Engram", "team": "DEN", "pos": "TE", "salary": 3700},
            {"week": 5, "name": "Isaiah Davis", "team": "NYJ", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Justice Hill", "team": "BAL", "pos": "RB", "salary": 5000},
            {"week": 5, "name": "Rashod Bateman", "team": "BAL", "pos": "WR", "salary": 4500},
            {"week": 5, "name": "Xavier Legette", "team": "CAR", "pos": "WR", "salary": 3500},
            {"week": 5, "name": "Bhayshul Tuten", "team": "JAX", "pos": "RB", "salary": 4900},
            {"week": 5, "name": "Ollie Gordon II", "team": "MIA", "pos": "RB", "salary": 4800},
            {"week": 5, "name": "Dyami Brown", "team": "JAX", "pos": "WR", "salary": 4100},
            {"week": 5, "name": "Cade Otton", "team": "TB", "pos": "TE", "salary": 3300},
            {"week": 5, "name": "Trevor Etienne", "team": "CAR", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Adonai Mitchell", "team": "IND", "pos": "WR", "salary": 3600},
            {"week": 5, "name": "Ray Davis", "team": "BUF", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Brandin Cooks", "team": "NO", "pos": "WR", "salary": 3500},
            {"week": 5, "name": "AJ Barner", "team": "SEA", "pos": "TE", "salary": 3100},
            {"week": 5, "name": "Blake Corum", "team": "LAR", "pos": "RB", "salary": 4500},
            {"week": 5, "name": "Noah Fant", "team": "CIN", "pos": "TE", "salary": 3100},
            {"week": 5, "name": "Isaiah Likely", "team": "BAL", "pos": "TE", "salary": 3000},
            {"week": 5, "name": "Tyquan Thornton", "team": "KC", "pos": "WR", "salary": 4200},
            {"week": 5, "name": "Jaylin Lane", "team": "WAS", "pos": "WR", "salary": 3100},
            {"week": 5, "name": "Cedrick Wilson Jr.", "team": "NO", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Jerome Ford", "team": "CLE", "pos": "RB", "salary": 4300},
            {"week": 5, "name": "Jayden Higgins", "team": "HOU", "pos": "WR", "salary": 3800},
            {"week": 5, "name": "DeMario Douglas", "team": "NE", "pos": "WR", "salary": 3500},
            {"week": 5, "name": "Nick Westbrook-Ikhine", "team": "MIA", "pos": "WR", "salary": 3400},
            {"week": 5, "name": "Zavier Scott", "team": "MIN", "pos": "RB", "salary": 4400},
            {"week": 5, "name": "Jack Bech", "team": "LV", "pos": "WR", "salary": 3200},
            {"week": 5, "name": "Josh Reynolds", "team": "NYJ", "pos": "WR", "salary": 3500},
            {"week": 5, "name": "Kendre Miller", "team": "NO", "pos": "RB", "salary": 4400},
            {"week": 5, "name": "Devin Singletary", "team": "NYG", "pos": "RB", "salary": 4500},
            {"week": 5, "name": "Mike Gesicki", "team": "CIN", "pos": "TE", "salary": 3200},
            {"week": 5, "name": "Oronde Gadsden", "team": "LAC", "pos": "TE", "salary": 2700},
            {"week": 5, "name": "Jalen Nailor", "team": "MIN", "pos": "WR", "salary": 3300},
            {"week": 5, "name": "Parker Washington", "team": "JAX", "pos": "WR", "salary": 3600},
            {"week": 5, "name": "Ty Johnson", "team": "BUF", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Raheem Mostert", "team": "LV", "pos": "RB", "salary": 4200},
            {"week": 5, "name": "Adam Thielen", "team": "MIN", "pos": "WR", "salary": 3500},
            {"week": 5, "name": "Tyler Lockett", "team": "TEN", "pos": "WR", "salary": 3400},
            {"week": 5, "name": "Brian Robinson Jr.", "team": "SF", "pos": "RB", "salary": 4100},
            {"week": 5, "name": "Jamari Thrash", "team": "CLE", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Xavier Hutchinson", "team": "HOU", "pos": "WR", "salary": 3300},
            {"week": 5, "name": "Andrei Iosivas", "team": "CIN", "pos": "WR", "salary": 3200},
            {"week": 5, "name": "Tyler Johnson", "team": "NYJ", "pos": "WR", "salary": 3300},
            {"week": 5, "name": "Ian Thomas", "team": "LV", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Antonio Gibson", "team": "NE", "pos": "RB", "salary": 4300},
            {"week": 5, "name": "Foster Moreau", "team": "NO", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Jalin Hyatt", "team": "NYG", "pos": "WR", "salary": 3300},
            {"week": 5, "name": "Chris Moore", "team": "WAS", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Elijah Arroyo", "team": "SEA", "pos": "TE", "salary": 2600},
            {"week": 5, "name": "Brycen Tremayne", "team": "CAR", "pos": "WR", "salary": 3100},
            {"week": 5, "name": "Marquez Valdes-Scantling", "team": "SF", "pos": "WR", "salary": 3100},
            {"week": 5, "name": "Tre' Harris", "team": "LAC", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Jordan Whittington", "team": "LAR", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Allen Lazard", "team": "NYJ", "pos": "WR", "salary": 3400},
            {"week": 5, "name": "Mack Hollins", "team": "NE", "pos": "WR", "salary": 3300},
            {"week": 5, "name": "Austin Hooper", "team": "NE", "pos": "TE", "salary": 3000},
            {"week": 5, "name": "Greg Dortch", "team": "ARI", "pos": "WR", "salary": 3400},
            {"week": 5, "name": "Skyy Moore", "team": "SF", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Davis Allen", "team": "LAR", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Gunnar Helm", "team": "TEN", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Hassan Haskins", "team": "LAC", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Noah Gray", "team": "KC", "pos": "TE", "salary": 2800},
            {"week": 5, "name": "Kyle Williams", "team": "NE", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Jaylin Noel", "team": "HOU", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Kalif Raymond", "team": "DET", "pos": "WR", "salary": 3300},
            {"week": 5, "name": "Jahan Dotson", "team": "PHI", "pos": "WR", "salary": 3400},
            {"week": 5, "name": "Colby Parkinson", "team": "LAR", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "DeAndre Hopkins", "team": "BAL", "pos": "WR", "salary": 4400},
            {"week": 5, "name": "Tutu Atwell", "team": "LAR", "pos": "WR", "salary": 3200},
            {"week": 5, "name": "Kyle Juszczyk", "team": "SF", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Isaac TeSlaa", "team": "DET", "pos": "WR", "salary": 3100},
            {"week": 5, "name": "Taysom Hill", "team": "NO", "pos": "QB", "salary": 3000},
            {"week": 5, "name": "Luke Farrell", "team": "SF", "pos": "TE", "salary": 2700},
            {"week": 5, "name": "Chimere Dike", "team": "TEN", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Samaje Perine", "team": "CIN", "pos": "RB", "salary": 4100},
            {"week": 5, "name": "Tez Johnson", "team": "TB", "pos": "WR", "salary": 3100},
            {"week": 5, "name": "Dawson Knox", "team": "BUF", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Jaydon Blue", "team": "DAL", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Zay Jones", "team": "ARI", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Tyler Conklin", "team": "LAC", "pos": "TE", "salary": 2600},
            {"week": 5, "name": "Dylan Sampson", "team": "CLE", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Brashard Smith", "team": "KC", "pos": "RB", "salary": 4200},
            {"week": 5, "name": "Luke Schoonmaker", "team": "DAL", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Jalen Royals", "team": "KC", "pos": "WR", "salary": 3200},
            {"week": 5, "name": "Albert Okwuegbunam", "team": "LV", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Jeremy Ruckert", "team": "NYJ", "pos": "TE", "salary": 2600},
            {"week": 5, "name": "Adam Trautman", "team": "DEN", "pos": "TE", "salary": 2800},
            {"week": 5, "name": "Ryan Flournoy", "team": "DAL", "pos": "WR", "salary": 3100},
            {"week": 5, "name": "Julian Hill", "team": "MIA", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Arian Smith", "team": "NYJ", "pos": "WR", "salary": 3200},
            {"week": 5, "name": "Johnny Mundt", "team": "JAX", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Josh Oliver", "team": "MIN", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Tylan Wallace", "team": "BAL", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Elijah Higgins", "team": "ARI", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Daniel Bellinger", "team": "NYG", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Devontez Walker", "team": "BAL", "pos": "WR", "salary": 3200},
            {"week": 5, "name": "Brock Wright", "team": "DET", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Will Shipley", "team": "PHI", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Curtis Samuel", "team": "BUF", "pos": "WR", "salary": 3100},
            {"week": 5, "name": "Tahj Washington", "team": "MIA", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Devaughn Vele", "team": "NO", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Drew Sample", "team": "CIN", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Dominic Lovett", "team": "DET", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "DJ Giddens", "team": "IND", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Grant Calcaterra", "team": "PHI", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Drew Ogletree", "team": "IND", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Hunter Long", "team": "JAX", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "John Bates", "team": "WAS", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Jack Stoll", "team": "NO", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Mitchell Tinsley", "team": "CIN", "pos": "WR", "salary": 3100},
            {"week": 5, "name": "Cody Schrader", "team": "JAX", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Alec Ingold", "team": "MIA", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Beaux Collins", "team": "NYG", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Tyler Badie", "team": "DEN", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Andrew Beck", "team": "NYJ", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Jake Bobo", "team": "SEA", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Brevyn Spann-Ford", "team": "DAL", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Russell Wilson", "team": "NYG", "pos": "QB", "salary": 4000},
            {"week": 5, "name": "Travis Vokolek", "team": "ARI", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Tip Reiman", "team": "ARI", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Ryan Miller", "team": "TB", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Ashton Dulin", "team": "IND", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Nate Adkins", "team": "DEN", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Mitchell Evans", "team": "CAR", "pos": "TE", "salary": 2700},
            {"week": 5, "name": "Tyrod Taylor", "team": "NYJ", "pos": "QB", "salary": 4600},
            {"week": 5, "name": "Blake Whiteheart", "team": "CLE", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Tanner Conner", "team": "MIA", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Pat Bryant", "team": "DEN", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "LeQuint Allen Jr.", "team": "JAX", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Terrance Ferguson", "team": "LAR", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Keaton Mitchell", "team": "BAL", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Van Jefferson", "team": "TEN", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Thomas Fidone II", "team": "NYG", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Isaac Guerendo", "team": "SF", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "DeeJay Dallas", "team": "CAR", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Dee Eskridge", "team": "MIA", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Jackson Hawes", "team": "BUF", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Payne Durham", "team": "TB", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "John Metchie III", "team": "PHI", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Charlie Kolar", "team": "BAL", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Jalen Milroe", "team": "SEA", "pos": "QB", "salary": 4000},
            {"week": 5, "name": "Eric Saubert", "team": "SEA", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Jack Westover", "team": "NE", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Nikko Remigio", "team": "KC", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Zamir White", "team": "LV", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Hunter Luepke", "team": "DAL", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Bam Knight", "team": "ARI", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "C.J. Ham", "team": "MIN", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Jimmy Horn Jr.", "team": "CAR", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Ameer Abdullah", "team": "IND", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Kameron Johnson", "team": "TB", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Keandre Lambert-Smith", "team": "LAC", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Anthony Gould", "team": "IND", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Kenny Pickett", "team": "LV", "pos": "QB", "salary": 4000},
            {"week": 5, "name": "Charlie Jones", "team": "CIN", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Ben Sinnott", "team": "WAS", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Dare Ogunbowale", "team": "HOU", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Kylen Granson", "team": "PHI", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Chris Manhertz", "team": "NYG", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Julius Chestnut", "team": "TEN", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Tahj Brooks", "team": "CIN", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "LaJohntay Wester", "team": "BAL", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Mason Tipton", "team": "NO", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "A.J. Dillon", "team": "PHI", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Trent Sherfield Sr.", "team": "DEN", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Will Mallory", "team": "IND", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Tai Felton", "team": "MIN", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Tanner Hudson", "team": "CIN", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Dylan Laube", "team": "LV", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Joe Flacco", "team": "CLE", "pos": "QB", "salary": 4500},
            {"week": 5, "name": "Khalil Herbert", "team": "NYJ", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Anthony Richardson Sr.", "team": "IND", "pos": "QB", "salary": 4000},
            {"week": 5, "name": "George Holani", "team": "SEA", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Marcus Mariota", "team": "WAS", "pos": "QB", "salary": 5000},
            {"week": 5, "name": "Craig Reynolds", "team": "DET", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Jared Wiley", "team": "KC", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Josh Williams", "team": "TB", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "James Mitchell", "team": "CAR", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Tank Bigsby", "team": "PHI", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Tim Patrick", "team": "JAX", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Xavier Smith", "team": "LAR", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Devin Culp", "team": "TB", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Dareke Young", "team": "SEA", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Mo Alie-Cox", "team": "IND", "pos": "TE", "salary": 2500},
            {"week": 5, "name": "Justin Shorter", "team": "LV", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Malachi Corley", "team": "CLE", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Tyler Huntley", "team": "BAL", "pos": "QB", "salary": 4300},
            {"week": 5, "name": "Gunner Olszewski", "team": "NYG", "pos": "WR", "salary": 3000},
            {"week": 5, "name": "Tyler Shough", "team": "NO", "pos": "QB", "salary": 4300},
            {"week": 5, "name": "Gardner Minshew", "team": "KC", "pos": "QB", "salary": 4000},
            {"week": 5, "name": "Zach Wilson", "team": "MIA", "pos": "QB", "salary": 4500},
            {"week": 5, "name": "Davis Mills", "team": "HOU", "pos": "QB", "salary": 4000},
            {"week": 5, "name": "Brett Rypien", "team": "CIN", "pos": "QB", "salary": 4000},
            {"week": 5, "name": "Cam Akers", "team": "MIN", "pos": "RB", "salary": 4000},
            {"week": 5, "name": "Mitchell Trubisky", "team": "BUF", "pos": "QB", "salary": 4000},
            
            # Week 6 data
            {"week": 6, "name": "Christian McCaffrey", "team": "SF", "pos": "RB", "salary": 8700},
            {"week": 6, "name": "Josh Allen", "team": "BUF", "pos": "QB", "salary": 8100},
            {"week": 6, "name": "Lamar Jackson", "team": "BAL", "pos": "QB", "salary": 7600},
            {"week": 6, "name": "De'Von Achane", "team": "MIA", "pos": "RB", "salary": 7400},
            {"week": 6, "name": "Puka Nacua", "team": "LAR", "pos": "WR", "salary": 8500},
            {"week": 6, "name": "Jalen Hurts", "team": "PHI", "pos": "QB", "salary": 6900},
            {"week": 6, "name": "Patrick Mahomes", "team": "KC", "pos": "QB", "salary": 6700},
            {"week": 6, "name": "Jonathan Taylor", "team": "IND", "pos": "RB", "salary": 8100},
            {"week": 6, "name": "Bijan Robinson", "team": "ATL", "pos": "RB", "salary": 8300},
            {"week": 6, "name": "Jahmyr Gibbs", "team": "DET", "pos": "RB", "salary": 7800},
            {"week": 6, "name": "Justin Herbert", "team": "LAC", "pos": "QB", "salary": 6200},
            {"week": 6, "name": "Jayden Daniels", "team": "WAS", "pos": "QB", "salary": 7100},
            {"week": 6, "name": "Amon-Ra St. Brown", "team": "DET", "pos": "WR", "salary": 8000},
            {"week": 6, "name": "Ja'Marr Chase", "team": "CIN", "pos": "WR", "salary": 8200},
            {"week": 6, "name": "Justin Jefferson", "team": "MIN", "pos": "WR", "salary": 7700},
            {"week": 6, "name": "Malik Nabers", "team": "NYG", "pos": "WR", "salary": 7200},
            {"week": 6, "name": "Jaxson Dart", "team": "NYG", "pos": "QB", "salary": 5400},
            {"week": 6, "name": "Cam Skattebo", "team": "NYG", "pos": "RB", "salary": 6100},
            {"week": 6, "name": "Darius Slayton", "team": "NYG", "pos": "WR", "salary": 3800},
            {"week": 6, "name": "Theo Johnson", "team": "NYG", "pos": "TE", "salary": 3000},
            {"week": 6, "name": "Wan'Dale Robinson", "team": "NYG", "pos": "WR", "salary": 4200},
            {"week": 6, "name": "Tyrone Tracy Jr.", "team": "NYG", "pos": "RB", "salary": 5200},
            {"week": 6, "name": "Saquon Barkley", "team": "PHI", "pos": "RB", "salary": 7600},
            {"week": 6, "name": "Derrick Henry", "team": "BAL", "pos": "RB", "salary": 7100},
            {"week": 6, "name": "James Cook", "team": "BUF", "pos": "RB", "salary": 7500},
            {"week": 6, "name": "Omarion Hampton", "team": "LAC", "pos": "RB", "salary": 6600},
            {"week": 6, "name": "Jaxon Smith-Njigba", "team": "SEA", "pos": "WR", "salary": 7200},
            {"week": 6, "name": "Drake Maye", "team": "NE", "pos": "QB", "salary": 6100},
            {"week": 6, "name": "Brock Purdy", "team": "SF", "pos": "QB", "salary": 6300},
            {"week": 6, "name": "Baker Mayfield", "team": "TB", "pos": "QB", "salary": 6400},
            {"week": 6, "name": "Dak Prescott", "team": "DAL", "pos": "QB", "salary": 6100},
            {"week": 6, "name": "Jared Goff", "team": "DET", "pos": "QB", "salary": 6600},
            {"week": 6, "name": "Kyler Murray", "team": "ARI", "pos": "QB", "salary": 6000},
            {"week": 6, "name": "Bo Nix", "team": "DEN", "pos": "QB", "salary": 5800},
            {"week": 6, "name": "Caleb Williams", "team": "CHI", "pos": "QB", "salary": 5900},
            {"week": 6, "name": "Daniel Jones", "team": "IND", "pos": "QB", "salary": 5900},
            {"week": 6, "name": "Justin Fields", "team": "NYJ", "pos": "QB", "salary": 5700},
            {"week": 6, "name": "Jordan Love", "team": "GB", "pos": "QB", "salary": 6300},
            {"week": 6, "name": "Matthew Stafford", "team": "LAR", "pos": "QB", "salary": 6000},
            {"week": 6, "name": "Trevor Lawrence", "team": "JAX", "pos": "QB", "salary": 5300},
            {"week": 6, "name": "C.J. Stroud", "team": "HOU", "pos": "QB", "salary": 5400},
            {"week": 6, "name": "Geno Smith", "team": "LV", "pos": "QB", "salary": 5500},
            {"week": 6, "name": "Sam Darnold", "team": "SEA", "pos": "QB", "salary": 5100},
            {"week": 6, "name": "Tua Tagovailoa", "team": "MIA", "pos": "QB", "salary": 5300},
            {"week": 6, "name": "Marcus Mariota", "team": "WAS", "pos": "QB", "salary": 5100},
            {"week": 6, "name": "Bryce Young", "team": "CAR", "pos": "QB", "salary": 5000},
            {"week": 6, "name": "Aaron Rodgers", "team": "PIT", "pos": "QB", "salary": 5400},
            {"week": 6, "name": "Joe Flacco", "team": "CLE", "pos": "QB", "salary": 4800},
            {"week": 6, "name": "Michael Penix Jr.", "team": "ATL", "pos": "QB", "salary": 5200},
            {"week": 6, "name": "Spencer Rattler", "team": "NO", "pos": "QB", "salary": 4800},
            {"week": 6, "name": "Cameron Ward", "team": "TEN", "pos": "QB", "salary": 4900},
            {"week": 6, "name": "Josh Jacobs", "team": "GB", "pos": "RB", "salary": 6900},
            {"week": 6, "name": "Bucky Irving", "team": "TB", "pos": "RB", "salary": 7000},
            {"week": 6, "name": "Kenneth Walker III", "team": "SEA", "pos": "RB", "salary": 6600},
            {"week": 6, "name": "Kyren Williams", "team": "LAR", "pos": "RB", "salary": 6400},
            {"week": 6, "name": "Chuba Hubbard", "team": "CAR", "pos": "RB", "salary": 6100},
            {"week": 6, "name": "Jordan Mason", "team": "MIN", "pos": "RB", "salary": 6500},
            {"week": 6, "name": "J.K. Dobbins", "team": "DEN", "pos": "RB", "salary": 5900},
            {"week": 6, "name": "Travis Etienne Jr.", "team": "JAX", "pos": "RB", "salary": 5900},
            {"week": 6, "name": "Alvin Kamara", "team": "NO", "pos": "RB", "salary": 6200},
            {"week": 6, "name": "David Montgomery", "team": "DET", "pos": "RB", "salary": 5800},
            {"week": 6, "name": "Tony Pollard", "team": "TEN", "pos": "RB", "salary": 5700},
            {"week": 6, "name": "Breece Hall", "team": "NYJ", "pos": "RB", "salary": 5800},
            {"week": 6, "name": "Chase Brown", "team": "CIN", "pos": "RB", "salary": 6700},
            {"week": 6, "name": "Ashton Jeanty", "team": "LV", "pos": "RB", "salary": 6300},
            {"week": 6, "name": "Trey Benson", "team": "ARI", "pos": "RB", "salary": 5600},
            {"week": 6, "name": "Javonte Williams", "team": "DAL", "pos": "RB", "salary": 6000},
            {"week": 6, "name": "D'Andre Swift", "team": "CHI", "pos": "RB", "salary": 5500},
            {"week": 6, "name": "Braelon Allen", "team": "NYJ", "pos": "RB", "salary": 5300},
            {"week": 6, "name": "Quinshon Judkins", "team": "CLE", "pos": "RB", "salary": 5600},
            {"week": 6, "name": "Brian Robinson Jr.", "team": "SF", "pos": "RB", "salary": 4600},
            {"week": 6, "name": "Will Shipley", "team": "PHI", "pos": "RB", "salary": 4400},
            {"week": 6, "name": "Tyreek Hill", "team": "MIA", "pos": "WR", "salary": 6700},
            {"week": 6, "name": "George Pickens", "team": "DAL", "pos": "WR", "salary": 6700},
            {"week": 6, "name": "Nico Collins", "team": "HOU", "pos": "WR", "salary": 7600},
            {"week": 6, "name": "Davante Adams", "team": "LAR", "pos": "WR", "salary": 6400},
            {"week": 6, "name": "A.J. Brown", "team": "PHI", "pos": "WR", "salary": 6600},
            {"week": 6, "name": "Courtland Sutton", "team": "DEN", "pos": "WR", "salary": 6300},
            {"week": 6, "name": "Garrett Wilson", "team": "NYJ", "pos": "WR", "salary": 6400},
            {"week": 6, "name": "Drake London", "team": "ATL", "pos": "WR", "salary": 5900},
            {"week": 6, "name": "DeVonta Smith", "team": "PHI", "pos": "WR", "salary": 5600},
            {"week": 6, "name": "Ladd McConkey", "team": "LAC", "pos": "WR", "salary": 6700},
            {"week": 6, "name": "Zay Flowers", "team": "BAL", "pos": "WR", "salary": 6900},
            {"week": 6, "name": "DJ Moore", "team": "CHI", "pos": "WR", "salary": 5800},
            {"week": 6, "name": "Brian Thomas Jr.", "team": "JAX", "pos": "WR", "salary": 6300},
            {"week": 6, "name": "Jaylen Waddle", "team": "MIA", "pos": "WR", "salary": 5700},
            {"week": 6, "name": "Rome Odunze", "team": "CHI", "pos": "WR", "salary": 6500},
            {"week": 6, "name": "Deebo Samuel Sr.", "team": "WAS", "pos": "WR", "salary": 6200},
            {"week": 6, "name": "Emeka Egbuka", "team": "TB", "pos": "WR", "salary": 7000},
            {"week": 6, "name": "Tee Higgins", "team": "CIN", "pos": "WR", "salary": 6000},
            {"week": 6, "name": "Chris Olave", "team": "NO", "pos": "WR", "salary": 5300},
            {"week": 6, "name": "Michael Pittman Jr.", "team": "IND", "pos": "WR", "salary": 5300},
            {"week": 6, "name": "Keenan Allen", "team": "LAC", "pos": "WR", "salary": 5500},
            {"week": 6, "name": "Ricky Pearsall", "team": "SF", "pos": "WR", "salary": 5900},
            {"week": 6, "name": "Tetairoa McMillan", "team": "CAR", "pos": "WR", "salary": 6100},
            {"week": 6, "name": "Jerry Jeudy", "team": "CLE", "pos": "WR", "salary": 5100},
            {"week": 6, "name": "Jakobi Meyers", "team": "LV", "pos": "WR", "salary": 5600},
            {"week": 6, "name": "DeAndre Hopkins", "team": "BAL", "pos": "WR", "salary": 4700},
            {"week": 6, "name": "Jahan Dotson", "team": "PHI", "pos": "WR", "salary": 3500},
            {"week": 6, "name": "Trey McBride", "team": "ARI", "pos": "TE", "salary": 5800},
            {"week": 6, "name": "Brock Bowers", "team": "LV", "pos": "TE", "salary": 6000},
            {"week": 6, "name": "Tyler Warren", "team": "IND", "pos": "TE", "salary": 4800},
            {"week": 6, "name": "Tucker Kraft", "team": "GB", "pos": "TE", "salary": 4900},
            {"week": 6, "name": "Dalton Kincaid", "team": "BUF", "pos": "TE", "salary": 4500},
            {"week": 6, "name": "Mark Andrews", "team": "BAL", "pos": "TE", "salary": 4700},
            {"week": 6, "name": "Sam LaPorta", "team": "DET", "pos": "TE", "salary": 4600},
            {"week": 6, "name": "Travis Kelce", "team": "KC", "pos": "TE", "salary": 5300},
            {"week": 6, "name": "Cade Stover", "team": "HOU", "pos": "TE", "salary": 3400},
            {"week": 6, "name": "Jake Ferguson", "team": "DAL", "pos": "TE", "salary": 3800},
            {"week": 6, "name": "Dallas Goedert", "team": "PHI", "pos": "TE", "salary": 4200},
            {"week": 6, "name": "Kyle Pitts", "team": "ATL", "pos": "TE", "salary": 3900},
            {"week": 6, "name": "Mike Gesicki", "team": "CIN", "pos": "TE", "salary": 3100},
            {"week": 6, "name": "Pat Freiermuth", "team": "PIT", "pos": "TE", "salary": 3500},
            {"week": 6, "name": "Jonnu Smith", "team": "MIA", "pos": "TE", "salary": 3600},
            {"week": 6, "name": "Zach Ertz", "team": "WAS", "pos": "TE", "salary": 3300},
            {"week": 6, "name": "Colby Parkinson", "team": "LAR", "pos": "TE", "salary": 2700},
            {"week": 6, "name": "Luke Musgrave", "team": "GB", "pos": "TE", "salary": 2700},
            {"week": 6, "name": "Dawson Knox", "team": "BUF", "pos": "TE", "salary": 2700},
            {"week": 6, "name": "Ben Sinnott", "team": "WAS", "pos": "TE", "salary": 2700},
            {"week": 6, "name": "Hunter Henry", "team": "NE", "pos": "TE", "salary": 3400},
            {"week": 6, "name": "Tyler Conklin", "team": "LAC", "pos": "TE", "salary": 2900}
        ]
        
        # Use the global connection
        # Clear existing data for weeks 4 and 5 of 2025
        conn.execute("DELETE FROM draftkings_pricing WHERE season = 2025 AND week IN (4, 5)")
        
        # Insert new pricing data
        inserted_count = 0
        updated_count = 0
        for player in pricing_data:
            try:
                # Generate a unique ID for the record
                record_id = f"{player['name']}_{player['team']}_{2025}_{player['week']}"
                conn.execute("""
                    INSERT INTO draftkings_pricing 
                    (id, player_name, team, position, season, week, salary, dk_player_id, created_at) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    hash(record_id) % 2147483647,  # Generate a positive integer ID
                    player["name"], 
                    player["team"], 
                    player["pos"], 
                    2025, 
                    player["week"], 
                    player["salary"],
                    '',  # dk_player_id
                    datetime.now(timezone.utc)
                ))
                inserted_count += 1
            except Exception:
                # Handle duplicate entries by updating existing records
                try:
                    conn.execute("""
                        UPDATE draftkings_pricing 
                        SET salary = ?, created_at = ?
                        WHERE player_name = ? AND team = ? AND season = ? AND week = ?
                    """, (
                        player["salary"],
                        datetime.now(timezone.utc),
                        player["name"], 
                        player["team"], 
                        2025, 
                        player["week"]
                    ))
                    updated_count += 1
                except Exception as e2:
                    print(f"Error updating {player['name']}: {str(e2)}")
        
        # Commit the transaction
        conn.commit()
        
        print("✅ DraftKings pricing data loaded successfully from Google Sheets")
        print(f"✅ Loaded {inserted_count + updated_count} salary records for weeks 4 and 5, 2025 season")
        
    except Exception as e:
        print(f"❌ Error loading DraftKings pricing: {str(e)}")
        raise


async def scrape_draftkings_salaries_from_fantasypros():
    """Scrape current DraftKings salaries from FantasyPros website"""
    try:
        url = "https://www.fantasypros.com/daily-fantasy/nfl/draftkings-salary-changes.php"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        logging.info(f"Scraping DraftKings salaries from FantasyPros...")
        
        # Fetch the page
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Parse HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the main data table
        table = None
        table_selectors = [
            ('id', 'data'),
            ('id', 'salary-changes-table'),
            ('class', 'table'),
            ('class', 'player-salary-table')
        ]
        
        for selector_type, selector_value in table_selectors:
            if selector_type == 'id':
                table = soup.find('table', {'id': selector_value})
            else:
                table = soup.find('table', class_=selector_value)
            
            if table:
                logging.info(f"Found table using {selector_type}='{selector_value}'")
                break
        
        if not table:
            # Try finding any table
            tables = soup.find_all('table')
            if tables:
                table = tables[0]  # Use first table found
                logging.info(f"Using first table found ({len(tables)} tables total)")
            else:
                logging.error("Could not find any salary table on FantasyPros page")
                return {
                    'success': False,
                    'message': 'Could not find salary table on page',
                    'count': 0
                }
        
        players_data = []
        
        # Find table body
        tbody = table.find('tbody')
        if tbody:
            rows = tbody.find_all('tr')
        else:
            # Skip header row if no tbody
            all_rows = table.find_all('tr')
            rows = all_rows[1:] if len(all_rows) > 1 else all_rows
        
        logging.info(f"Found {len(rows)} rows in salary table")
        
        # Determine current week from page
        current_week = 8  # Default
        current_season = 2025
        
        # Try to extract week number from page heading
        heading = soup.find('h1')
        if heading:
            week_match = re.search(r'Week\s+(\d+)', heading.get_text())
            if week_match:
                current_week = int(week_match.group(1))
                logging.info(f"Detected current week: {current_week}")
        
        for idx, row in enumerate(rows):
            try:
                cols = row.find_all('td')
                if len(cols) < 5:  # Skip rows without enough data
                    continue
                
                # Column structure (from crawl tool output):
                # 0: ECR (rank)
                # 1: Player (name with team-pos in parentheses)
                # 2: Kickoff time
                # 3: Opponent
                # 4: This Week (current salary) 
                # 5: Last Week (previous salary)
                # 6: Difference
                
                # Get player cell (typically column 1)
                player_cell_text = ""
                for col in cols[0:3]:  # Check first few columns for player data
                    text = col.get_text(strip=True)
                    # Look for pattern: "Name (TEAM - POS)" or just "(TEAM - POS)"
                    if '(' in text and '-' in text and ')' in text:
                        player_cell_text = text
                        break
                
                if not player_cell_text:
                    continue
                
                # Parse player name and team-position from format: "Player Name (TEAM - POS)"
                # Example: "Oronde Gadsden II (LAC - TE)"
                match = re.match(r'(.+?)\s*\(([A-Z]{2,3})\s*-\s*([A-Z]{2,3})\)', player_cell_text)
                
                if not match:
                    # Try alternative: just "(TEAM - POS)" without name
                    match = re.match(r'\(([A-Z]{2,3})\s*-\s*([A-Z]{2,3})\)', player_cell_text)
                    if match:
                        team = match.group(1)
                        position = match.group(2)
                        # Try to get name from previous column or link
                        player_name = cols[1].find('a').get_text(strip=True) if cols[1].find('a') else "Unknown"
                    else:
                        continue
                else:
                    player_name = match.group(1).strip()
                    team = match.group(2)
                    position = match.group(3)
                
                # Only include skill positions
                if position not in SKILL_POSITIONS:
                    continue
                
                # Extract salary from "This Week" column (usually column 4 or 5)
                salary = 0
                for col in cols[3:]:  # Check columns starting from opponent/time
                    text = col.get_text(strip=True)
                    salary_match = re.search(r'\$([0-9,]+)', text)
                    if salary_match:
                        try:
                            salary = int(salary_match.group(1).replace(',', ''))
                            if salary > 1000:  # Valid salary found
                                break
                        except:
                            pass
                
                if salary == 0 or salary < 2000:  # Skip invalid salaries
                    continue
                
                players_data.append({
                    'player_name': player_name,
                    'team': team,
                    'position': position,
                    'salary': salary,
                    'season': current_season,
                    'week': current_week
                })
                
            except Exception as e:
                logging.warning(f"Error parsing row {idx}: {e}")
                continue
        
        logging.info(f"Parsed {len(players_data)} player salary records")
        
        if not players_data:
            logging.warning("No player salary data scraped from FantasyPros")
            return {
                'success': False,
                'message': 'No salary data found on page',
                'count': 0
            }
        
        # Insert into database
        inserted_count = 0
        updated_count = 0
        
        for player in players_data:
            try:
                # Try to insert
                conn.execute("""
                    INSERT INTO draftkings_pricing 
                    (id, player_name, team, position, season, week, salary, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    str(uuid.uuid4()),
                    player['player_name'],
                    player['team'],
                    player['position'],
                    player['season'],
                    player['week'],
                    player['salary'],
                    datetime.now(timezone.utc)
                ))
                inserted_count += 1
            except Exception as e:
                # If exists, update
                if 'Constraint Error' in str(e) or 'UNIQUE' in str(e):
                    try:
                        conn.execute("""
                            UPDATE draftkings_pricing 
                            SET salary = ?, created_at = ?
                            WHERE player_name = ? AND team = ? AND season = ? AND week = ?
                        """, (
                            player['salary'],
                            datetime.now(timezone.utc),
                            player['player_name'],
                            player['team'],
                            player['season'],
                            player['week']
                        ))
                        updated_count += 1
                    except Exception as e2:
                        logging.error(f"Error updating {player['player_name']}: {e2}")
        
        conn.commit()
        
        total_count = inserted_count + updated_count
        logging.info(f"✅ Scraped and loaded {total_count} DraftKings salaries from FantasyPros")
        
        return {
            'success': True,
            'message': f'Successfully scraped {total_count} player salaries for Week {current_week}',
            'count': total_count,
            'inserted': inserted_count,
            'updated': updated_count,
            'season': current_season,
            'week': current_week
        }
        
    except Exception as e:
        logging.error(f"Error scraping FantasyPros: {e}")
        logging.error(traceback.format_exc())
        return {
            'success': False,
            'message': f'Error: {str(e)}',
            'count': 0
        }

# Initialize scheduler for automatic weekly updates
scheduler = BackgroundScheduler()

def scheduled_scrape_salaries():
    """Scheduled job to scrape DraftKings salaries every Wednesday"""
    logging.info("Running scheduled DraftKings salary scrape...")
    try:
        # Run the async function in a new event loop
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(scrape_draftkings_salaries_from_fantasypros())
        loop.close()
        logging.info(f"Scheduled scrape completed: {result}")
    except Exception as e:
        logging.error(f"Scheduled scrape failed: {e}")

def init_database():
    """Initialize DuckDB tables"""
    try:
        # Create players table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                player_id VARCHAR PRIMARY KEY,
                player_name VARCHAR,
                position VARCHAR,
                team VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create weekly_stats table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weekly_stats (
                id VARCHAR PRIMARY KEY,
                player_id VARCHAR,
                player_name VARCHAR,
                position VARCHAR,
                team VARCHAR,
                season INTEGER,
                week INTEGER,
                opponent VARCHAR,
                passing_yards DOUBLE DEFAULT 0,
                passing_tds INTEGER DEFAULT 0,
                interceptions INTEGER DEFAULT 0,
                rushing_yards DOUBLE DEFAULT 0,
                rushing_tds INTEGER DEFAULT 0,
                receptions INTEGER DEFAULT 0,
                receiving_yards DOUBLE DEFAULT 0,
                receiving_tds INTEGER DEFAULT 0,
                targets INTEGER DEFAULT 0,
                fumbles_lost INTEGER DEFAULT 0,
                fantasy_points DOUBLE DEFAULT 0,
                snap_percentage DOUBLE,
                dk_salary VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(player_id, season, week)
            )
        """)
        
        # Create enhanced snap_counts table with proper schema
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snap_counts (
                id VARCHAR PRIMARY KEY,
                player_id VARCHAR,
                player_name VARCHAR,
                team VARCHAR,
                season INTEGER,
                week INTEGER,
                offense_snaps INTEGER DEFAULT 0,
                offense_pct DOUBLE DEFAULT 0,
                defense_snaps INTEGER DEFAULT 0,
                defense_pct DOUBLE DEFAULT 0,
                st_snaps INTEGER DEFAULT 0,
                st_pct DOUBLE DEFAULT 0,
                position VARCHAR,
                game_id VARCHAR,
                opponent_team VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(player_id, season, week)
            )
        """)
        
        # Create DraftKings pricing table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS draftkings_pricing (
                id INTEGER PRIMARY KEY,
                player_name VARCHAR NOT NULL,
                team VARCHAR NOT NULL,
                position VARCHAR NOT NULL,
                season INTEGER NOT NULL,
                week INTEGER NOT NULL,
                salary INTEGER NOT NULL,
                dk_player_id VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(player_name, team, season, week)
            )
        """)
        
        # Create indexes for better performance
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snap_counts_season_week 
            ON snap_counts(season, week)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_snap_counts_player 
            ON snap_counts(player_id, season, week)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dk_pricing_season_week 
            ON draftkings_pricing(season, week)
        """)
        
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_dk_pricing_player 
            ON draftkings_pricing(player_name, team)
        """)
        
        # Create skill position view for snap counts
        conn.execute("""
            CREATE OR REPLACE VIEW skill_snap_counts AS
            SELECT *
            FROM snap_counts
            WHERE offense_snaps > 0
              AND position IN ('QB', 'RB', 'WR', 'TE')
        """)
        
        logging.info("Database initialized successfully")
    except Exception as e:
        logging.error(f"Error initializing database: {e}")
        raise

def load_nfl_data_sync(seasons: List[int]) -> Dict[str, int]:
    """Load NFL data synchronously for async wrapper"""
    try:
        total_records = 0
        snap_records = 0
        
        for season in seasons:
            logging.info(f"Loading data for season {season}")
            
            # Load player stats
            try:
                player_stats = nfl.load_player_stats(seasons=[season])
                logging.info(f"Player stats type: {type(player_stats)}, length: {len(player_stats) if player_stats is not None else 'None'}")
                
                if player_stats is not None and len(player_stats) > 0:
                    # Convert Polars to Pandas for easier processing
                    player_stats_pd = player_stats.to_pandas()
                    
                    # Filter for relevant positions
                    relevant_positions = ['QB', 'RB', 'WR', 'TE']
                    filtered_stats = player_stats_pd[player_stats_pd['position'].isin(relevant_positions)].copy()
                    
                    # Use existing fantasy_points column (or fantasy_points_ppr for PPR)
                    if 'fantasy_points_ppr' in filtered_stats.columns:
                        filtered_stats['fantasy_points'] = filtered_stats['fantasy_points_ppr']
                    elif 'fantasy_points' not in filtered_stats.columns:
                        # Fallback to calculation if neither column exists
                        filtered_stats['fantasy_points'] = filtered_stats.apply(
                            lambda row: calculate_fantasy_points(row.to_dict()), axis=1
                        )
                    
                    # Create unique ID for each record
                    filtered_stats['id'] = filtered_stats.apply(
                        lambda row: f"{row['player_id']}_{row['season']}_{row['week']}", axis=1
                    )
                    
                    # Insert into database
                    conn.execute("DELETE FROM weekly_stats WHERE season = ?", [season])
                    conn.register('stats_df', filtered_stats)
                    conn.execute("""
                        INSERT INTO weekly_stats 
                        SELECT 
                            id,
                            player_id,
                            player_display_name as player_name,
                            position,
                            team,
                            season,
                            week,
                            opponent_team as opponent,
                            COALESCE(passing_yards, 0) as passing_yards,
                            COALESCE(passing_tds, 0) as passing_tds,
                            COALESCE(passing_interceptions, 0) as interceptions,
                            COALESCE(rushing_yards, 0) as rushing_yards,
                            COALESCE(rushing_tds, 0) as rushing_tds,
                            COALESCE(receptions, 0) as receptions,
                            COALESCE(receiving_yards, 0) as receiving_yards,
                            COALESCE(receiving_tds, 0) as receiving_tds,
                            COALESCE(targets, 0) as targets,
                            COALESCE(rushing_fumbles_lost, 0) + COALESCE(receiving_fumbles_lost, 0) as fumbles_lost,
                            fantasy_points,
                            NULL as snap_percentage,
                            NULL as dk_salary,
                            CURRENT_TIMESTAMP as created_at
                        FROM stats_df
                    """)
                    
                    records_count = len(filtered_stats)
                    total_records += records_count
                    logging.info(f"Loaded {records_count} player stat records for season {season}")
                    
            except Exception as e:
                logging.error(f"Error loading player stats for season {season}: {e}")
                continue
        
        # Load snap counts for all seasons at once (more efficient)
        try:
            logging.info(f"Loading snap counts for seasons: {seasons}")
            snap_result = load_snap_counts_for_seasons(seasons)
            if snap_result['success']:
                snap_records = snap_result['total_loaded']
                logging.info(f"Successfully loaded {snap_records} snap count records")
            else:
                logging.error(f"Failed to load snap counts: {snap_result.get('error', 'Unknown error')}")
        except Exception as e:
            logging.error(f"Error loading snap counts: {e}")
        
        # Update weekly_stats with snap percentages from the enhanced snap_counts table
        try:
            # First, let's see what snap count data we actually have
            snap_check = conn.execute("SELECT COUNT(*) FROM snap_counts").fetchone()[0]
            logging.info(f"Total snap count records available: {snap_check}")
            
            if snap_check > 0:
                # Update with more flexible matching
                updates = conn.execute("""
                    UPDATE weekly_stats 
                    SET snap_percentage = (
                        SELECT sc.offense_pct 
                        FROM snap_counts sc 
                        WHERE (
                            UPPER(TRIM(sc.player_name)) = UPPER(TRIM(weekly_stats.player_name))
                        )
                          AND sc.team = weekly_stats.team
                          AND sc.season = weekly_stats.season 
                          AND sc.week = weekly_stats.week
                        ORDER BY sc.offense_pct DESC
                        LIMIT 1
                    )
                    WHERE EXISTS (
                        SELECT 1 FROM snap_counts sc 
                        WHERE (
                            UPPER(TRIM(sc.player_name)) = UPPER(TRIM(weekly_stats.player_name))
                        )
                          AND sc.team = weekly_stats.team
                          AND sc.season = weekly_stats.season 
                          AND sc.week = weekly_stats.week
                    )
                """)
                logging.info("Updated weekly_stats with snap percentages")
                
                # Check how many got updated
                updated_count = conn.execute("SELECT COUNT(*) FROM weekly_stats WHERE snap_percentage IS NOT NULL AND snap_percentage > 0").fetchone()[0]
                logging.info(f"Players with snap percentages after update: {updated_count}")
            else:
                logging.warning("No snap count data available to update")
        except Exception as e:
            logging.error(f"Error updating snap percentages: {e}")
        
        # Update weekly_stats with DraftKings salaries from cached data
        try:
            # Check available pricing data
            pricing_check = conn.execute("SELECT COUNT(*) FROM draftkings_pricing").fetchone()[0]
            logging.info(f"Total DraftKings pricing records available: {pricing_check}")
            
            if pricing_check > 0:
                # Clear any existing dk_salary data that might be showing dates
                conn.execute("UPDATE weekly_stats SET dk_salary = NULL")
                
                # Update with proper salary formatting
                updates = conn.execute("""
                    UPDATE weekly_stats 
                    SET dk_salary = (
                        SELECT CASE 
                            WHEN dp.salary >= 10000 THEN '$' || CAST(ROUND(dp.salary / 1000.0, 1) AS VARCHAR) || 'k'
                            WHEN dp.salary >= 1000 THEN '$' || CAST(ROUND(dp.salary / 1000.0, 1) AS VARCHAR) || 'k'
                            WHEN dp.salary > 0 THEN '$' || CAST(dp.salary AS VARCHAR)
                            ELSE NULL
                        END
                        FROM draftkings_pricing dp 
                        WHERE UPPER(TRIM(dp.player_name)) = UPPER(TRIM(weekly_stats.player_name))
                          AND dp.team = weekly_stats.team 
                          AND dp.season = weekly_stats.season 
                          AND dp.week = weekly_stats.week
                        ORDER BY dp.salary DESC
                        LIMIT 1
                    )
                    WHERE EXISTS (
                        SELECT 1 FROM draftkings_pricing dp 
                        WHERE UPPER(TRIM(dp.player_name)) = UPPER(TRIM(weekly_stats.player_name))
                          AND dp.team = weekly_stats.team 
                          AND dp.season = weekly_stats.season 
                          AND dp.week = weekly_stats.week
                    )
                """)
                logging.info("Updated weekly_stats with DraftKings salaries")
                
                # Check how many got updated
                updated_count = conn.execute("SELECT COUNT(*) FROM weekly_stats WHERE dk_salary IS NOT NULL").fetchone()[0]
                logging.info(f"Players with DraftKings salaries after update: {updated_count}")
            else:
                logging.warning("No DraftKings pricing data available to update")
        except Exception as e:
            logging.error(f"Error updating DraftKings salaries: {e}")
        
        return {
            "total_records": total_records,
            "snap_records": snap_records
        }
        
    except Exception as e:
        logging.error(f"Error in load_nfl_data_sync: {e}")
        logging.error(traceback.format_exc())
        raise

async def load_nfl_data(seasons: List[int]) -> Dict[str, int]:
    """Load NFL data asynchronously"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, load_nfl_data_sync, seasons)

async def load_historical_pricing_async() -> Dict:
    """Load historical DraftKings pricing asynchronously"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, load_historical_draftkings_data)

async def load_snap_counts_async(seasons: List[int]) -> Dict:
    """Load snap counts asynchronously"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, load_snap_counts_for_seasons, seasons)

# API Endpoints
@api_router.get("/")
async def root():
    return {"message": "Fantasy Football Database API", "version": "1.0.0"}

@api_router.get("/nfl-teams")
async def get_nfl_teams():
    """Get all NFL teams"""
    return {"teams": NFL_TEAMS}

@api_router.get("/players", response_model=List[PlayerStats])
async def get_players(
    season: Optional[int] = Query(None, description="Season year (2024, 2025)"),
    week: Optional[int] = Query(None, description="Week number (1-18)"),
    week_start: Optional[int] = Query(None, description="Start week for cumulative range"),
    week_end: Optional[int] = Query(None, description="End week for cumulative range"),
    position: Optional[str] = Query(None, description="Position (QB, RB, WR, TE)"),
    team: Optional[str] = Query(None, description="Team abbreviation"),
    limit: int = Query(500, description="Maximum number of records to return"),
    offset: int = Query(0, description="Number of records to skip")
):
    """Get player statistics with optional filters. Supports cumulative stats across week ranges."""
    try:
        # Determine if we're doing a week range query
        is_range_query = week_start is not None and week_end is not None
        
        if is_range_query:
            # Cumulative query for week ranges
            query = """
                SELECT 
                    ws.player_id,
                    ws.player_name,
                    ws.position,
                    ws.team,
                    ws.season,
                    NULL as week,
                    NULL as opponent,
                    SUM(ws.passing_yards) as passing_yards,
                    SUM(ws.passing_tds) as passing_tds,
                    SUM(ws.interceptions) as interceptions,
                    SUM(ws.rushing_yards) as rushing_yards,
                    SUM(ws.rushing_tds) as rushing_tds,
                    SUM(ws.receptions) as receptions,
                    SUM(ws.receiving_yards) as receiving_yards,
                    SUM(ws.receiving_tds) as receiving_tds,
                    SUM(ws.targets) as targets,
                    SUM(ws.fumbles_lost) as fumbles_lost,
                    SUM(ws.fantasy_points) as fantasy_points,
                    AVG(CASE WHEN sc.offense_snaps IS NOT NULL THEN sc.offense_pct ELSE NULL END) as snap_percentage,
                    SUM(CASE WHEN sc.offense_snaps IS NOT NULL THEN sc.offense_snaps ELSE 0 END) as snap_count,
                    NULL as dk_salary
                FROM weekly_stats ws
                LEFT JOIN skill_snap_counts sc ON (
                    (LOWER(TRIM(ws.player_name)) = LOWER(TRIM(sc.player_name))) OR
                    (LOWER(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(ws.player_name, '\\s+(Jr\\.?|Sr\\.?|III|II|IV)\\s*$', '', 'i'), '\\.', '', 'g'))) = 
                     LOWER(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(sc.player_name, '\\s+(Jr\\.?|Sr\\.?|III|II|IV)\\s*$', '', 'i'), '\\.', '', 'g'))))
                ) AND ws.season = sc.season AND ws.week = sc.week
                WHERE 1=1
            """
            
            params = []
            
            if season:
                query += " AND ws.season = ?"
                params.append(season)
            
            # Add week range filter
            query += " AND ws.week >= ? AND ws.week <= ?"
            params.append(week_start)
            params.append(week_end)
            
            if position:
                query += " AND ws.position = ?"
                params.append(position.upper())
            
            if team:
                query += " AND ws.team = ?"
                params.append(team.upper())
            
            # Group by player for aggregation
            query += " GROUP BY ws.player_id, ws.player_name, ws.position, ws.team, ws.season"
            query += " ORDER BY fantasy_points DESC, ws.player_name"
            query += f" LIMIT {limit} OFFSET {offset}"
            
        else:
            # Original single-week or all-weeks query
            query = """
                SELECT 
                    ws.player_id,
                    ws.player_name,
                    ws.position,
                    ws.team,
                    ws.season,
                    ws.week,
                    ws.opponent,
                    ws.passing_yards,
                    ws.passing_tds,
                    ws.interceptions,
                    ws.rushing_yards,
                    ws.rushing_tds,
                    ws.receptions,
                    ws.receiving_yards,
                    ws.receiving_tds,
                    ws.targets,
                    ws.fumbles_lost,
                    ws.fantasy_points,
                    COALESCE(sc.offense_snaps, CAST(ws.snap_percentage * 100 AS INTEGER)) as snap_percentage,
                    COALESCE(sc.offense_snaps, 0) as snap_count,
                    COALESCE(dp.salary, NULL) as dk_salary
                FROM weekly_stats ws
                LEFT JOIN skill_snap_counts sc ON (
                    (LOWER(TRIM(ws.player_name)) = LOWER(TRIM(sc.player_name))) OR
                    (LOWER(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(ws.player_name, '\\s+(Jr\\.?|Sr\\.?|III|II|IV)\\s*$', '', 'i'), '\\.', '', 'g'))) = 
                     LOWER(TRIM(REGEXP_REPLACE(REGEXP_REPLACE(sc.player_name, '\\s+(Jr\\.?|Sr\\.?|III|II|IV)\\s*$', '', 'i'), '\\.', '', 'g'))))
                ) AND ws.season = sc.season AND ws.week = sc.week
                LEFT JOIN draftkings_pricing dp ON LOWER(TRIM(ws.player_name)) = LOWER(TRIM(dp.player_name))
                    AND ws.team = dp.team
                    AND ws.season = dp.season 
                    AND ws.week = dp.week
                WHERE 1=1
            """
            
            params = []
            
            if season:
                query += " AND ws.season = ?"
                params.append(season)
            
            if week:
                query += " AND ws.week = ?"
                params.append(week)
            
            if position:
                query += " AND ws.position = ?"
                params.append(position.upper())
            
            if team:
                query += " AND ws.team = ?"
                params.append(team.upper())
            
            query += " ORDER BY ws.fantasy_points DESC, ws.player_name"
            query += f" LIMIT {limit} OFFSET {offset}"
        
        result = conn.execute(query, params).fetchall()
        columns = [desc[0] for desc in conn.description]
        
        players = []
        for row in result:
            player_data = dict(zip(columns, row))
            players.append(PlayerStats(**player_data))
        
        return players
        
    except Exception as e:
        logging.error(f"Error fetching players: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching players: {str(e)}")

@api_router.post("/load-sheets-pricing")
async def load_sheets_pricing():
    """Load DraftKings pricing from Google Sheets data"""
    try:
        await load_draftkings_pricing_from_sheets()
        return {"message": "DraftKings pricing data loaded successfully from Google Sheets"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading pricing data: {str(e)}")

@api_router.get("/stats/summary")
async def get_stats_summary():
    """Get summary statistics about the database"""
    try:
        # Get total records
        total_stats = conn.execute("SELECT COUNT(*) FROM weekly_stats").fetchone()[0]
        total_snaps = conn.execute("SELECT COUNT(*) FROM snap_counts").fetchone()[0]
        total_pricing = conn.execute("SELECT COUNT(*) FROM draftkings_pricing").fetchone()[0]
        
        # Get seasons available
        seasons = conn.execute("SELECT DISTINCT season FROM weekly_stats ORDER BY season DESC").fetchall()
        seasons = [row[0] for row in seasons]
        
        # Get weeks available for current season
        if seasons:
            current_season = seasons[0]
            weeks = conn.execute(
                "SELECT DISTINCT week FROM weekly_stats WHERE season = ? ORDER BY week", 
                [current_season]
            ).fetchall()
            weeks = [row[0] for row in weeks]
        else:
            weeks = []
        
        # Get position counts
        position_counts = conn.execute("""
            SELECT position, COUNT(*) as count 
            FROM weekly_stats 
            GROUP BY position 
            ORDER BY count DESC
        """).fetchall()
        
        # Get snap count statistics
        snap_stats = conn.execute("""
            SELECT COUNT(*) as players_with_snaps
            FROM weekly_stats 
            WHERE snap_percentage IS NOT NULL AND snap_percentage > 0
        """).fetchone()[0]
        
        # Get snap count coverage by season
        snap_coverage = conn.execute("""
            SELECT season, COUNT(*) as snap_count
            FROM snap_counts 
            GROUP BY season
            ORDER BY season DESC
        """).fetchall()
        
        # Get DraftKings pricing statistics
        pricing_stats = conn.execute("""
            SELECT COUNT(*) as players_with_pricing
            FROM weekly_stats 
            WHERE dk_salary IS NOT NULL
        """).fetchone()[0]
        
        # Get pricing coverage by season/week
        pricing_coverage = conn.execute("""
            SELECT season, week, COUNT(*) as pricing_count
            FROM draftkings_pricing 
            GROUP BY season, week
            ORDER BY season DESC, week DESC
            LIMIT 10
        """).fetchall()
        
        return {
            "total_player_stats": total_stats,
            "total_snap_counts": total_snaps,
            "total_pricing_records": total_pricing,
            "players_with_snap_data": snap_stats,
            "players_with_pricing": pricing_stats,
            "seasons_available": seasons,
            "weeks_available": weeks,
            "position_counts": {row[0]: row[1] for row in position_counts},
            "snap_coverage": [{"season": row[0], "count": row[1]} for row in snap_coverage],
            "pricing_coverage": [{"season": row[0], "week": row[1], "count": row[2]} for row in pricing_coverage],
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logging.error(f"Error getting stats summary: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting summary: {str(e)}")

@api_router.post("/refresh-data", response_model=RefreshResponse)
async def refresh_data(
    seasons: Optional[List[int]] = Query([2024, 2025], description="Seasons to refresh")
):
    """Refresh NFL data from nflverse sources including snap counts"""
    try:
        logging.info(f"Starting data refresh for seasons: {seasons}")
        
        result = await load_nfl_data(seasons)
        
        return RefreshResponse(
            success=True,
            message=f"Successfully refreshed data for seasons {seasons}",
            records_loaded=result["total_records"],
            snap_records_loaded=result.get("snap_records", 0),
            timestamp=datetime.now(timezone.utc)
        )
        
    except Exception as e:
        logging.error(f"Error refreshing data: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, 
            detail=f"Error refreshing data: {str(e)}"
        )

@api_router.post("/load-snap-counts", response_model=SnapCountsResponse)
async def load_snap_counts_endpoint(
    seasons: Optional[List[int]] = Query([2024, 2025], description="Seasons to load snap counts for")
):
    """Load snap counts for specified seasons"""
    try:
        logging.info(f"Starting snap counts load for seasons: {seasons}")
        
        result = await load_snap_counts_async(seasons)
        
        if result['success']:
            return SnapCountsResponse(
                success=True,
                message=f"Successfully loaded snap counts for seasons {seasons}",
                records_loaded=result['total_loaded'],
                timestamp=datetime.now(timezone.utc)
            )
        else:
            return SnapCountsResponse(
                success=False,
                message=f"Failed to load snap counts: {result.get('error', 'Unknown error')}",
                records_loaded=0,
                timestamp=datetime.now(timezone.utc)
            )
        
    except Exception as e:
        logging.error(f"Error loading snap counts: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, 
            detail=f"Error loading snap counts: {str(e)}"
        )

@api_router.post("/load-historical-pricing", response_model=DraftKingsResponse)
async def load_historical_pricing():
    """Load historical DraftKings pricing data from 2024 to current"""
    try:
        logging.info("Starting historical DraftKings pricing data load")
        
        result = await load_historical_pricing_async()
        
        return DraftKingsResponse(
            success=True,
            message=f"Successfully loaded historical pricing data. Cached {result['total_cached']} records from {result['weeks_processed']} weeks.",
            records_processed=result['total_cached'],
            data={
                'weeks_processed': result['weeks_processed'],
                'errors': result['errors'][:5]  # Show first 5 errors
            },
            timestamp=datetime.now(timezone.utc)
        )
        
    except Exception as e:
        logging.error(f"Error loading historical pricing: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, 
            detail=f"Error loading historical pricing: {str(e)}"
        )

@api_router.post("/load-sheets-pricing", response_model=DraftKingsResponse)
async def load_sheets_pricing():
    """Load DraftKings pricing data from Google Sheets for weeks 4 and 5"""
    try:
        logging.info("Starting DraftKings pricing data load from Google Sheets")
        
        await load_draftkings_pricing_from_sheets()
        
        # Get the actual count of records loaded
        count_result = conn.execute("SELECT COUNT(*) FROM draftkings_pricing WHERE season = 2025 AND week IN (4, 5)").fetchone()
        
        return DraftKingsResponse(
            success=True,
            message=f"Successfully loaded DraftKings pricing data from Google Sheets for weeks 4 and 5, 2025 season. {count_result[0]} records loaded.",
            records_processed=count_result[0],
            timestamp=datetime.now(timezone.utc)
        )
        
    except Exception as e:
        logging.error(f"Error loading sheets pricing: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, 
            detail=f"Error loading sheets pricing: {str(e)}"
        )


@api_router.post("/scrape-draftkings-salaries", response_model=DraftKingsResponse)
async def scrape_salaries():
    """Manually trigger DraftKings salary scraping from FantasyPros"""
    try:
        logging.info("Manual DraftKings salary scrape triggered")
        
        result = await scrape_draftkings_salaries_from_fantasypros()
        
        if result['success']:
            return DraftKingsResponse(
                success=True,
                message=result['message'],
                records_processed=result.get('count', 0),
                timestamp=datetime.now(timezone.utc),
                data={
                    'inserted': result.get('inserted', 0),
                    'updated': result.get('updated', 0),
                    'season': result.get('season'),
                    'week': result.get('week')
                }
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=result['message']
            )
            
    except Exception as e:
        logging.error(f"Error in manual salary scrape: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Error scraping salaries: {str(e)}"
        )

@api_router.post("/load-excel-salaries", response_model=DraftKingsResponse)
async def load_excel_salaries():
    """Load DraftKings salaries from Excel file"""
    try:
        logging.info("Loading DraftKings salaries from Excel file")
        
        excel_file = ROOT_DIR / "dk_salaries.xlsx"
        if not excel_file.exists():
            raise HTTPException(status_code=404, detail="Excel file not found")
        
        # Read Excel file
        xl = pd.ExcelFile(excel_file)
        logging.info(f"Found sheets: {xl.sheet_names}")
        
        total_inserted = 0
        total_updated = 0
        total_skipped = 0
        
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(excel_file, sheet_name=sheet_name)
            logging.info(f"Processing sheet: {sheet_name}, rows: {len(df)}, columns: {df.columns.tolist()}")
            
            for idx, row in df.iterrows():
                try:
                    # Extract data - try different column name variations
                    week = row.get('Week', row.get('WEEK', row.get('week', 1)))
                    name = row.get('NAME', row.get('name', row.get('Player', '')))
                    team = row.get('TEAM', row.get('team', row.get('Team', '')))
                    position = row.get('POS', row.get('pos', row.get('Position', '')))
                    salary_raw = row.get('$', row.get('Salary', row.get('salary', row.get('DK $', 0))))
                    
                    # Clean up data
                    if pd.isna(name) or name == '':
                        total_skipped += 1
                        continue
                        
                    name = str(name).strip()
                    team = str(team).strip().upper() if not pd.isna(team) else 'UNK'
                    position = str(position).strip().upper() if not pd.isna(position) else 'UNK'
                    
                    # Parse salary - handle string format like "7400"
                    if pd.isna(salary_raw):
                        salary = 0
                    elif isinstance(salary_raw, str):
                        # Remove any non-numeric characters except comma and period
                        cleaned = ''.join(c for c in salary_raw if c.isdigit() or c in '.,')
                        cleaned = cleaned.replace(',', '')
                        try:
                            salary = int(float(cleaned)) if cleaned else 0
                        except:
                            salary = 0
                    else:
                        try:
                            salary = int(float(salary_raw))
                        except:
                            salary = 0
                    
                    if salary == 0 or salary < 2000:
                        total_skipped += 1
                        continue
                    
                    # Only QB, RB, WR, TE
                    if position not in ['QB', 'RB', 'WR', 'TE']:
                        total_skipped += 1
                        continue
                    
                    # Try to insert
                    try:
                        conn.execute("""
                            INSERT INTO draftkings_pricing 
                            (player_name, team, position, season, week, salary, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            name,
                            team,
                            position,
                            2025,
                            int(week),
                            salary,
                            datetime.now(timezone.utc)
                        ))
                        total_inserted += 1
                    except Exception as e:
                        # If exists, update
                        if 'Constraint Error' in str(e) or 'UNIQUE' in str(e):
                            conn.execute("""
                                UPDATE draftkings_pricing 
                                SET salary = ?, created_at = ?
                                WHERE player_name = ? AND team = ? AND season = ? AND week = ?
                            """, (
                                salary,
                                datetime.now(timezone.utc),
                                name,
                                team,
                                2025,
                                int(week)
                            ))
                            total_updated += 1
                        else:
                            logging.warning(f"Database error on row {idx}: {e}")
                            total_skipped += 1
                            
                except Exception as e:
                    logging.warning(f"Error processing row {idx}: {e}")
                    total_skipped += 1
            
            conn.commit()
        
        total_count = total_inserted + total_updated
        logging.info(f"Excel load complete: {total_inserted} inserted, {total_updated} updated, {total_skipped} skipped")
        
        return DraftKingsResponse(
            success=True,
            message=f"Successfully loaded {total_count} salary records from Excel (Weeks 1-8)",
            records_processed=total_count,
            timestamp=datetime.now(timezone.utc),
            data={
                'inserted': total_inserted,
                'updated': total_updated,
                'skipped': total_skipped
            }
        )
        
    except Exception as e:
        logging.error(f"Error loading Excel salaries: {e}")
        logging.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"Error loading Excel: {str(e)}"
        )

@api_router.get("/draftkings-pricing-summary")
async def get_pricing_summary():
    """Get summary of DraftKings pricing data"""
    try:
        # Get weekly breakdown
        weekly_data = conn.execute("""
            SELECT week, COUNT(*) as count, COUNT(DISTINCT position) as positions,
                   MIN(salary) as min_salary, MAX(salary) as max_salary
            FROM draftkings_pricing
            WHERE season = 2025
            GROUP BY week
            ORDER BY week
        """).fetchall()
        
        # Get sample data from latest week
        latest_week = conn.execute("""
            SELECT MAX(week) FROM draftkings_pricing WHERE season = 2025
        """).fetchone()[0] if weekly_data else 0
        
        sample_data = []
        if latest_week:
            samples = conn.execute("""
                SELECT player_name, team, position, salary
                FROM draftkings_pricing
                WHERE season = 2025 AND week = ?
                ORDER BY salary DESC
                LIMIT 20
            """, [latest_week]).fetchall()
            
            sample_data = [
                {
                    'player': row[0],
                    'team': row[1],
                    'pos': row[2],
                    'salary': row[3]
                }
                for row in samples
            ]
        
        return {
            'success': True,
            'season': 2025,
            'weeks': [
                {
                    'week': row[0],
                    'player_count': row[1],
                    'positions': row[2],
                    'min_salary': row[3],
                    'max_salary': row[4]
                }
                for row in weekly_data
            ],
            'latest_week': latest_week,
            'sample_players': sample_data
        }
        
    except Exception as e:
        logging.error(f"Error getting pricing summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))
async def get_snap_counts(
    season: Optional[int] = Query(None, description="Season year"),
    week: Optional[int] = Query(None, description="Week number"),
    position: Optional[str] = Query(None, description="Position filter"),
    team: Optional[str] = Query(None, description="Team filter"),
    limit: int = Query(100, description="Maximum number of records to return")
):
    """Get snap counts data with filters"""
    try:
        query = "SELECT * FROM skill_snap_counts WHERE 1=1"
        params = []
        
        if season:
            query += " AND season = ?"
            params.append(season)
        
        if week:
            query += " AND week = ?"
            params.append(week)
        
        if position:
            query += " AND position = ?"
            params.append(position.upper())
        
        if team:
            query += " AND team = ?"
            params.append(team.upper())
        
        query += " ORDER BY season DESC, week DESC, offense_pct DESC"
        query += f" LIMIT {limit}"
        
        result = conn.execute(query, params).fetchall()
        columns = [desc[0] for desc in conn.description]
        
        snap_data = []
        for row in result:
            snap_data.append(dict(zip(columns, row)))
        
        return {
            "success": True,
            "data": snap_data,
            "count": len(snap_data)
        }
        
    except Exception as e:
        logging.error(f"Error getting snap counts: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting snap counts: {str(e)}")

@api_router.get("/draftkings-pricing", response_model=DraftKingsResponse)
async def get_draftkings_pricing(
    season: Optional[int] = Query(None, description="Season year"),
    week: Optional[int] = Query(None, description="Week number")
):
    """Get cached DraftKings pricing data"""
    try:
        query = "SELECT * FROM draftkings_pricing WHERE 1=1"
        params = []
        
        if season:
            query += " AND season = ?"
            params.append(season)
        
        if week:
            query += " AND week = ?"
            params.append(week)
        
        query += " ORDER BY season DESC, week DESC, salary DESC LIMIT 100"
        
        result = conn.execute(query, params).fetchall()
        columns = [desc[0] for desc in conn.description]
        
        pricing_data = []
        for row in result:
            pricing_data.append(dict(zip(columns, row)))
        
        return DraftKingsResponse(
            success=True,
            data={'pricing': pricing_data},
            message=f"Retrieved {len(pricing_data)} pricing records",
            records_processed=len(pricing_data),
            timestamp=datetime.now(timezone.utc)
        )
        
    except Exception as e:
        logging.error(f"Error getting DraftKings pricing: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Error getting DraftKings pricing: {str(e)}"
        )

@api_router.get("/top-performers")
async def get_top_performers(
    season: int = Query(2024, description="Season year"),
    position: Optional[str] = Query(None, description="Position filter"),
    week: Optional[int] = Query(None, description="Week filter (leave empty for season totals)"),
    limit: int = Query(20, description="Number of top performers to return")
):
    """Get top fantasy performers"""
    try:
        if week:
            # Single week performance
            query = """
                SELECT 
                    player_name,
                    position,
                    team,
                    week,
                    fantasy_points,
                    passing_yards,
                    passing_tds,
                    rushing_yards,
                    rushing_tds,
                    receptions,
                    receiving_yards,
                    receiving_tds,
                    snap_percentage,
                    dk_salary
                FROM weekly_stats
                WHERE season = ? AND week = ?
            """
            params = [season, week]
        else:
            # Season totals
            query = """
                SELECT 
                    player_name,
                    position,
                    team,
                    COUNT(*) as games_played,
                    SUM(fantasy_points) as fantasy_points,
                    AVG(fantasy_points) as avg_fantasy_points,
                    SUM(passing_yards) as passing_yards,
                    SUM(passing_tds) as passing_tds,
                    SUM(rushing_yards) as rushing_yards,
                    SUM(rushing_tds) as rushing_tds,
                    SUM(receptions) as receptions,
                    SUM(receiving_yards) as receiving_yards,
                    SUM(receiving_tds) as receiving_tds,
                    AVG(snap_percentage) as avg_snap_percentage
                FROM weekly_stats
                WHERE season = ?
                GROUP BY player_name, position, team
            """
            params = [season]
        
        if position:
            query += " AND position = ?"
            params.append(position.upper())
        
        query += " ORDER BY fantasy_points DESC"
        query += f" LIMIT {limit}"
        
        result = conn.execute(query, params).fetchall()
        columns = [desc[0] for desc in conn.description]
        
        performers = []
        for row in result:
            performer_data = dict(zip(columns, row))
            performers.append(performer_data)
        
        return performers
        
    except Exception as e:
        logging.error(f"Error getting top performers: {e}")
        raise HTTPException(status_code=500, detail=f"Error getting top performers: {str(e)}")

# Initialize database on startup
init_database()

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def load_nfl_data_background():
    """Background task to load NFL data on startup"""
    try:
        logger.info("Starting background NFL data load...")
        await load_nfl_data([2024, 2025])
        logger.info("Background NFL data load completed successfully")
    except Exception as e:
        logger.error(f"Background NFL data load failed: {e}")

@app.on_event("startup")
async def startup_event():
    logger.info("Fantasy Football Database API started successfully")
    
    # Start the scheduler for automatic Wednesday scraping
    scheduler.add_job(
        scheduled_scrape_salaries,
        CronTrigger(day_of_week='wed', hour=10, minute=0),  # Every Wednesday at 10 AM
        id='weekly_salary_scrape',
        replace_existing=True
    )
    scheduler.start()
    logger.info("Scheduler started: DraftKings salaries will be scraped every Wednesday at 10 AM")
    
    # Check if database has data, if not, auto-load
    try:
        result = conn.execute("SELECT COUNT(*) as count FROM weekly_stats WHERE season = 2025").fetchone()
        row_count = result[0] if result else 0
        
        if row_count < 100:  # If less than 100 records, database is likely empty or outdated
            logger.info(f"Database has only {row_count} records for 2025. Auto-loading NFL data...")
            # Don't await here, run in background
            asyncio.create_task(load_nfl_data_background())
        else:
            logger.info(f"Database already populated with {row_count} records for 2025 season")
            
        # Trigger immediate salary scrape on startup to get latest data
        logger.info("Triggering immediate DraftKings salary scrape...")
        asyncio.create_task(scrape_draftkings_salaries_from_fantasypros())
    except Exception as e:
        logger.warning(f"Could not check database status: {e}. Skipping auto-load.")

@app.on_event("shutdown")
async def shutdown_event():
    scheduler.shutdown(wait=False)
    conn.close()
    executor.shutdown(wait=True)
    logger.info("Fantasy Football Database API shutdown complete")
