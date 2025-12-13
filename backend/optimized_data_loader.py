"""
Optimized data loading module for NFL Hub backend.
This module provides efficient data loading with batch processing, transactions, and caching.
"""

import logging
import traceback
import time
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
import pandas as pd
import nflreadpy as nfl
import duckdb
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from functools import lru_cache
import hashlib

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

SKILL_POSITIONS = ['QB', 'RB', 'WR', 'TE']

class OptimizedDataLoader:
    """Optimized data loader with batch processing and caching"""
    
    def __init__(self, db_connection: duckdb.DuckDBPyConnection):
        self.conn = db_connection
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._name_cache = {}
        self._load_name_mappings()
    
    def _load_name_mappings(self):
        """Load existing name mappings into cache"""
        try:
            mappings = self.conn.execute(
                "SELECT source_name, target_name FROM player_name_mappings"
            ).fetchall()
            for source, target in mappings:
                self._name_cache[self.normalize_player_name(source)] = target
            logging.info(f"Loaded {len(self._name_cache)} name mappings into cache")
        except Exception as e:
            logging.warning(f"Could not load name mappings: {e}")
    
    @staticmethod
    @lru_cache(maxsize=10000)
    def normalize_player_name(name: str) -> str:
        """
        Normalize player names for better matching between data sources.
        Uses LRU cache for performance.
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
    
    def get_mapped_name(self, name: str) -> str:
        """Get mapped name from cache or return normalized name"""
        normalized = self.normalize_player_name(name)
        return self._name_cache.get(normalized, name)
    
    @staticmethod
    def calculate_fantasy_points_vectorized(df: pd.DataFrame) -> pd.Series:
        """Calculate DraftKings PPR fantasy points using vectorized operations"""
        points = pd.Series(0.0, index=df.index)
        
        # Passing
        if 'passing_yards' in df.columns:
            points += df['passing_yards'].fillna(0) * DRAFTKINGS_SCORING['passing_yards']
        if 'passing_tds' in df.columns:
            points += df['passing_tds'].fillna(0) * DRAFTKINGS_SCORING['passing_tds']
        if 'passing_interceptions' in df.columns:
            points += df['passing_interceptions'].fillna(0) * DRAFTKINGS_SCORING['interceptions']
        
        # Rushing
        if 'rushing_yards' in df.columns:
            points += df['rushing_yards'].fillna(0) * DRAFTKINGS_SCORING['rushing_yards']
        if 'rushing_tds' in df.columns:
            points += df['rushing_tds'].fillna(0) * DRAFTKINGS_SCORING['rushing_tds']
        
        # Receiving
        if 'receptions' in df.columns:
            points += df['receptions'].fillna(0) * DRAFTKINGS_SCORING['receptions']
        if 'receiving_yards' in df.columns:
            points += df['receiving_yards'].fillna(0) * DRAFTKINGS_SCORING['receiving_yards']
        if 'receiving_tds' in df.columns:
            points += df['receiving_tds'].fillna(0) * DRAFTKINGS_SCORING['receiving_tds']
        
        # Fumbles
        if 'rushing_fumbles_lost' in df.columns and 'receiving_fumbles_lost' in df.columns:
            points += (df['rushing_fumbles_lost'].fillna(0) + 
                      df['receiving_fumbles_lost'].fillna(0)) * DRAFTKINGS_SCORING['fumbles_lost']
        
        return points.round(2)
    
    def load_player_stats_optimized(self, seasons: List[int]) -> Dict[str, int]:
        """Load player stats with optimized batch processing"""
        try:
            logging.info(f"Loading player stats for seasons: {seasons}")
            start_time = time.time()
            
            # Load all seasons at once (more efficient than individual loads)
            player_stats = nfl.load_player_stats(seasons=seasons)
            
            if player_stats is None or len(player_stats) == 0:
                logging.warning("No player stats data returned")
                return {"total_records": 0}
            
            # Convert to pandas for processing
            player_stats_pd = player_stats.to_pandas()
            logging.info(f"Loaded {len(player_stats_pd)} raw player stat records")
            
            # Filter for relevant positions
            filtered_stats = player_stats_pd[
                player_stats_pd['position'].isin(SKILL_POSITIONS)
            ].copy()
            logging.info(f"After filtering for skill positions: {len(filtered_stats)} records")
            
            if len(filtered_stats) == 0:
                logging.warning("No skill position stats found")
                return {"total_records": 0}
            
            # Use vectorized fantasy points calculation
            if 'fantasy_points_ppr' in filtered_stats.columns:
                filtered_stats['fantasy_points'] = filtered_stats['fantasy_points_ppr']
            else:
                filtered_stats['fantasy_points'] = self.calculate_fantasy_points_vectorized(filtered_stats)
            
            # Create unique IDs efficiently
            filtered_stats['id'] = (
                filtered_stats['player_id'].astype(str) + '_' +
                filtered_stats['season'].astype(str) + '_' +
                filtered_stats['week'].astype(str)
            )
            
            # Normalize player names for better matching
            filtered_stats['normalized_name'] = filtered_stats['player_display_name'].apply(
                self.normalize_player_name
            )
            
            # Use transaction for atomic operation
            with self.conn.begin():
                # Delete existing data for these seasons
                seasons_str = ','.join(map(str, seasons))
                self.conn.execute(f"DELETE FROM weekly_stats WHERE season IN ({seasons_str})")
                
                # Register DataFrame and insert in one operation
                self.conn.register('stats_df', filtered_stats)
                self.conn.execute("""
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
                        CURRENT_TIMESTAMP as created_at,
                        NULL as dk_salary
                    FROM stats_df
                """)
            
            records_count = len(filtered_stats)
            elapsed_time = time.time() - start_time
            logging.info(f"Loaded {records_count} player stat records in {elapsed_time:.2f} seconds")
            
            return {"total_records": records_count}
            
        except Exception as e:
            logging.error(f"Error in load_player_stats_optimized: {e}")
            logging.error(traceback.format_exc())
            raise
    
    def load_snap_counts_optimized(self, seasons: List[int]) -> Dict[str, int]:
        """Load snap counts with optimized batch processing"""
        try:
            logging.info(f"Loading snap counts for seasons: {seasons}")
            start_time = time.time()
            
            # Load all seasons at once
            snap_counts_data = nfl.load_snap_counts(seasons=seasons)
            
            if snap_counts_data is None or len(snap_counts_data) == 0:
                logging.warning("No snap counts data returned")
                return {"total_loaded": 0}
            
            # Convert to pandas
            snap_counts_pd = snap_counts_data.to_pandas()
            logging.info(f"Loaded {len(snap_counts_pd)} raw snap count records")
            
            # Apply filters efficiently
            if 'game_type' in snap_counts_pd.columns:
                snap_counts_pd = snap_counts_pd[snap_counts_pd['game_type'] == 'REG']
            
            snap_counts_pd = snap_counts_pd[
                (snap_counts_pd['position'].isin(SKILL_POSITIONS)) &
                (snap_counts_pd['offense_snaps'] > 0)
            ]
            
            logging.info(f"After filtering: {len(snap_counts_pd)} records")
            
            if len(snap_counts_pd) == 0:
                logging.warning("No filtered snap counts found")
                return {"total_loaded": 0}
            
            # Create unique IDs efficiently
            snap_counts_pd['id'] = (
                snap_counts_pd['season'].astype(str) + '_' +
                snap_counts_pd['week'].astype(str) + '_' +
                snap_counts_pd['team'].astype(str) + '_' +
                snap_counts_pd['player'].str.replace(' ', '_')
            )
            
            # Use transaction for atomic operation
            with self.conn.begin():
                # Delete existing data for these seasons
                seasons_str = ','.join(map(str, seasons))
                self.conn.execute(f"DELETE FROM snap_counts WHERE season IN ({seasons_str})")
                
                # Register and insert
                self.conn.register('snap_counts_df', snap_counts_pd)
                self.conn.execute("""
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
            
            records_count = len(snap_counts_pd)
            elapsed_time = time.time() - start_time
            logging.info(f"Loaded {records_count} snap count records in {elapsed_time:.2f} seconds")
            
            return {"total_loaded": records_count}
            
        except Exception as e:
            logging.error(f"Error in load_snap_counts_optimized: {e}")
            logging.error(traceback.format_exc())
            raise
    
    def update_weekly_stats_with_joins(self) -> Dict[str, int]:
        """Update weekly_stats with snap percentages and salaries using optimized JOINs"""
        try:
            logging.info("Updating weekly_stats with snap percentages and salaries")
            start_time = time.time()
            
            # Single query to update both snap percentages and salaries
            with self.conn.begin():
                # Update snap percentages using efficient JOIN
                snap_updates = self.conn.execute("""
                    UPDATE weekly_stats 
                    SET snap_percentage = sc.offense_pct
                    FROM snap_counts sc 
                    WHERE weekly_stats.player_name = sc.player_name
                      AND weekly_stats.team = sc.team
                      AND weekly_stats.season = sc.season 
                      AND weekly_stats.week = sc.week
                """).fetchone()
                
                # Update DraftKings salaries using efficient JOIN
                salary_updates = self.conn.execute("""
                    UPDATE weekly_stats 
                    SET dk_salary = CASE 
                        WHEN dp.salary >= 10000 THEN '$' || CAST(ROUND(dp.salary / 1000.0, 1) AS VARCHAR) || 'k'
                        WHEN dp.salary >= 1000 THEN '$' || CAST(ROUND(dp.salary / 1000.0, 1) AS VARCHAR) || 'k'
                        WHEN dp.salary > 0 THEN '$' || CAST(dp.salary AS VARCHAR)
                        ELSE NULL
                    END
                    FROM draftkings_pricing dp 
                    WHERE weekly_stats.player_name = dp.player_name
                      AND weekly_stats.team = dp.team 
                      AND weekly_stats.season = dp.season 
                      AND weekly_stats.week = dp.week
                """).fetchone()
            
            # Get counts of updated records
            snap_count = self.conn.execute(
                "SELECT COUNT(*) FROM weekly_stats WHERE snap_percentage IS NOT NULL AND snap_percentage > 0"
            ).fetchone()[0]
            
            salary_count = self.conn.execute(
                "SELECT COUNT(*) FROM weekly_stats WHERE dk_salary IS NOT NULL"
            ).fetchone()[0]
            
            elapsed_time = time.time() - start_time
            logging.info(f"Updated {snap_count} records with snap percentages and {salary_count} with salaries in {elapsed_time:.2f} seconds")
            
            return {"snap_updates": snap_count, "salary_updates": salary_count}
            
        except Exception as e:
            logging.error(f"Error in update_weekly_stats_with_joins: {e}")
            logging.error(traceback.format_exc())
            raise
    
    def load_nfl_data_optimized(self, seasons: List[int]) -> Dict[str, int]:
        """Main optimized data loading function"""
        try:
            logging.info(f"Starting optimized data load for seasons: {seasons}")
            total_start_time = time.time()
            
            # Load player stats and snap counts in parallel
            with ThreadPoolExecutor(max_workers=2) as executor:
                stats_future = executor.submit(self.load_player_stats_optimized, seasons)
                snap_future = executor.submit(self.load_snap_counts_optimized, seasons)
                
                # Wait for both to complete
                stats_result = stats_future.result()
                snap_result = snap_future.result()
            
            # Update weekly_stats with joined data
            join_result = self.update_weekly_stats_with_joins()
            
            total_elapsed = time.time() - total_start_time
            logging.info(f"Completed optimized data load in {total_elapsed:.2f} seconds")
            
            return {
                "total_records": stats_result["total_records"],
                "snap_records": snap_result["total_loaded"],
                "snap_updates": join_result["snap_updates"],
                "salary_updates": join_result["salary_updates"]
            }
            
        except Exception as e:
            logging.error(f"Error in load_nfl_data_optimized: {e}")
            logging.error(traceback.format_exc())
            raise

class OptimizedAPIClient:
    """Optimized API client with rate limiting and caching"""
    
    def __init__(self, api_key: str, api_host: str):
        self.api_key = api_key
        self.api_host = api_host
        self.session = requests.Session()
        self.session.headers.update({
            "x-rapidapi-key": api_key,
            "x-rapidapi-host": api_host,
            "Content-Type": "application/json"
        })
        self._cache = {}
        self._last_request_time = 0
        self._min_request_interval = 0.1  # 100ms between requests
    
    def _rate_limit(self):
        """Implement rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        if time_since_last < self._min_request_interval:
            time.sleep(self._min_request_interval - time_since_last)
        self._last_request_time = time.time()
    
    def _get_cache_key(self, season: int, week: int) -> str:
        """Generate cache key for API response"""
        return f"dk_salaries_{season}_{week}"
    
    def fetch_draftkings_salaries_cached(self, season: int, week: int) -> Dict:
        """Fetch DraftKings salaries with caching and rate limiting"""
        cache_key = self._get_cache_key(season, week)
        
        # Check cache first
        if cache_key in self._cache:
            logging.info(f"Using cached DraftKings data for season {season}, week {week}")
            return self._cache[cache_key]
        
        # Rate limit API calls
        self._rate_limit()
        
        url = f"https://{self.api_host}/getDFSsalaries"
        querystring = {
            "week": str(week),
            "season": str(season),
            "site": "draftkings"
        }
        
        try:
            response = self.session.get(url, params=querystring, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            logging.info(f"DraftKings API response received for season {season}, week {week}")
            
            processed_data = []
            if 'body' in data and 'draftkings' in data['body']:
                for player in data['body']['draftkings']:
                    position = player.get('pos', '').upper()
                    if position in SKILL_POSITIONS:
                        # Parse salary
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
            
            result = {
                'success': True,
                'data': processed_data,
                'count': len(processed_data)
            }
            
            # Cache the result
            self._cache[cache_key] = result
            
            return result
            
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
    
    def batch_load_draftkings_data(self, season_week_pairs: List[Tuple[int, int]], 
                                   db_connection: duckdb.DuckDBPyConnection) -> Dict:
        """Load DraftKings data in batches with optimized database operations"""
        try:
            logging.info(f"Batch loading DraftKings data for {len(season_week_pairs)} season/week pairs")
            start_time = time.time()
            
            all_data = []
            successful_loads = 0
            failed_loads = 0
            
            # Fetch data for all season/week pairs
            for season, week in season_week_pairs:
                result = self.fetch_draftkings_salaries_cached(season, week)
                if result['success']:
                    all_data.extend(result['data'])
                    successful_loads += 1
                else:
                    failed_loads += 1
                    logging.warning(f"Failed to load data for season {season}, week {week}")
            
            if not all_data:
                logging.warning("No DraftKings data to load")
                return {
                    'success': False,
                    'message': 'No data retrieved',
                    'records_processed': 0
                }
            
            # Convert to DataFrame for efficient database operations
            df = pd.DataFrame(all_data)
            
            # Use transaction for atomic operation
            with db_connection.begin():
                # Clear existing data for these season/week pairs
                for season, week in season_week_pairs:
                    db_connection.execute(
                        "DELETE FROM draftkings_pricing WHERE season = ? AND week = ?",
                        [season, week]
                    )
                
                # Register DataFrame and insert all data at once
                db_connection.register('dk_pricing_df', df)
                db_connection.execute("""
                    INSERT INTO draftkings_pricing 
                    (player_name, team, position, season, week, salary, dk_player_id, created_at)
                    SELECT 
                        player_name, team, position, season, week, salary, dk_player_id,
                        CURRENT_TIMESTAMP as created_at
                    FROM dk_pricing_df
                """)
            
            elapsed_time = time.time() - start_time
            logging.info(f"Batch loaded {len(all_data)} DraftKings records in {elapsed_time:.2f} seconds")
            
            return {
                'success': True,
                'message': f'Successfully loaded {len(all_data)} records',
                'records_processed': len(all_data),
                'successful_loads': successful_loads,
                'failed_loads': failed_loads
            }
            
        except Exception as e:
            logging.error(f"Error in batch_load_draftkings_data: {e}")
            logging.error(traceback.format_exc())
            return {
                'success': False,
                'message': f'Error loading data: {str(e)}',
                'records_processed': 0
            }