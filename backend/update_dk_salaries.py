#!/usr/bin/env python3
"""
Script to update DraftKings salaries using RapidAPI for missing weeks
"""
import sys
from pathlib import Path
from datetime import datetime

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import functions from server.py
from server import (
    fetch_draftkings_salaries,
    cache_draftkings_pricing,
    conn,
    logging
)

def check_missing_weeks():
    """Check which weeks have stats but missing DK salaries"""
    # Get weeks with stats
    stats_weeks = conn.execute("""
        SELECT DISTINCT season, week
        FROM weekly_stats
        WHERE season = 2025
        ORDER BY week
    """).fetchall()

    # Get weeks with DK pricing
    pricing_weeks = conn.execute("""
        SELECT DISTINCT season, week
        FROM draftkings_pricing
        WHERE season = 2025
        ORDER BY week
    """).fetchall()

    stats_set = set(stats_weeks)
    pricing_set = set(pricing_weeks)

    missing = stats_set - pricing_set

    return sorted(list(missing), key=lambda x: x[1])

def main():
    """Main function to update DK salaries"""
    print("=" * 60)
    print("DraftKings Salary Update")
    print("=" * 60)
    print(f"Started at: {datetime.now()}")
    print()

    # Check database status
    print("Current database status:")
    print("-" * 60)

    stats_count = conn.execute("SELECT COUNT(*) FROM weekly_stats WHERE season = 2025").fetchone()[0]
    print(f"Total player stat records (2025): {stats_count}")

    latest_stats_week = conn.execute("SELECT MAX(week) FROM weekly_stats WHERE season = 2025").fetchone()[0]
    print(f"Latest week with stats: {latest_stats_week}")

    pricing_count = conn.execute("SELECT COUNT(*) FROM draftkings_pricing WHERE season = 2025").fetchone()[0]
    print(f"Total DK pricing records (2025): {pricing_count}")

    latest_pricing_week = conn.execute("SELECT MAX(week) FROM draftkings_pricing WHERE season = 2025").fetchone()[0]
    print(f"Latest week with DK salaries: {latest_pricing_week}")

    print()

    # Check missing weeks
    missing_weeks = check_missing_weeks()

    if not missing_weeks:
        print("✅ All weeks with stats already have DK salary data!")
        print()

        # Show summary by week
        print("Summary by week:")
        print("-" * 60)
        week_summary = conn.execute("""
            SELECT
                ws.week,
                COUNT(DISTINCT ws.player_id) as stat_players,
                COUNT(DISTINCT CASE WHEN ws.dk_salary IS NOT NULL THEN ws.player_id END) as salary_players
            FROM weekly_stats ws
            WHERE ws.season = 2025
            GROUP BY ws.week
            ORDER BY ws.week
        """).fetchall()

        for week, stat_players, salary_players in week_summary:
            pct = (salary_players / stat_players * 100) if stat_players > 0 else 0
            print(f"Week {week:2d}: {stat_players:3d} players, {salary_players:3d} with salaries ({pct:.0f}%)")
    else:
        print(f"⚠️  Found {len(missing_weeks)} week(s) with stats but missing DK salaries:")
        for season, week in missing_weeks:
            print(f"   - Season {season}, Week {week}")
        print()

        # Try to fetch missing weeks using RapidAPI
        print("Attempting to fetch missing weeks using RapidAPI...")
        print("-" * 60)

        for season, week in missing_weeks:
            print(f"\nFetching Season {season}, Week {week}...")
            try:
                result = fetch_draftkings_salaries(season, week)

                if result['success'] and result['data']:
                    cached = cache_draftkings_pricing(result['data'], season, week)
                    print(f"  ✅ Successfully cached {cached} DK salary records")

                    # Update weekly_stats with the new salaries
                    conn.execute("""
                        UPDATE weekly_stats
                        SET dk_salary = (
                            SELECT CAST(salary AS VARCHAR)
                            FROM draftkings_pricing dp
                            WHERE UPPER(TRIM(dp.player_name)) = UPPER(TRIM(weekly_stats.player_name))
                              AND dp.team = weekly_stats.team
                              AND dp.season = weekly_stats.season
                              AND dp.week = weekly_stats.week
                            LIMIT 1
                        )
                        WHERE season = ? AND week = ?
                          AND EXISTS (
                            SELECT 1 FROM draftkings_pricing dp
                            WHERE UPPER(TRIM(dp.player_name)) = UPPER(TRIM(weekly_stats.player_name))
                              AND dp.team = weekly_stats.team
                              AND dp.season = ?
                              AND dp.week = ?
                          )
                    """, [season, week, season, week])

                    updated_count = conn.execute(
                        "SELECT COUNT(*) FROM weekly_stats WHERE season = ? AND week = ? AND dk_salary IS NOT NULL",
                        [season, week]
                    ).fetchone()[0]

                    print(f"  ✅ Updated {updated_count} player records with DK salaries")
                else:
                    error = result.get('error', 'Unknown error')
                    print(f"  ❌ Failed to fetch data: {error}")

            except Exception as e:
                print(f"  ❌ Error: {e}")
                import traceback
                traceback.print_exc()

        print()
        print("=" * 60)
        print("Update completed!")
        print("=" * 60)

if __name__ == "__main__":
    main()
