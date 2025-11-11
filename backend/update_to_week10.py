#!/usr/bin/env python3
"""
Update NFL Hub database to Week 10 - comprehensive data refresh
"""
import sys
from pathlib import Path
from datetime import datetime
import traceback

sys.path.insert(0, str(Path(__file__).parent))

from server import (
    load_nfl_data_sync,
    fetch_draftkings_salaries,
    cache_draftkings_pricing,
    conn,
    logging
)

def check_current_status():
    """Check what data we currently have"""
    print("="*70)
    print("CURRENT DATABASE STATUS")
    print("="*70)

    # Check player stats
    stats = conn.execute("""
        SELECT season, MIN(week) as min_week, MAX(week) as max_week, COUNT(*) as total
        FROM weekly_stats
        WHERE season = 2025
        GROUP BY season
    """).fetchone()

    if stats:
        print(f"Player Stats: Season {stats[0]}, Weeks {stats[1]}-{stats[2]}, {stats[3]} records")
    else:
        print("Player Stats: No data for 2025")

    # Check DK pricing
    pricing = conn.execute("""
        SELECT season, MIN(week) as min_week, MAX(week) as max_week, COUNT(*) as total
        FROM draftkings_pricing
        WHERE season = 2025
        GROUP BY season
    """).fetchone()

    if pricing:
        print(f"DK Salaries: Season {pricing[0]}, Weeks {pricing[1]}-{pricing[2]}, {pricing[3]} records")
    else:
        print("DK Salaries: No data for 2025")

    print()
    return stats, pricing

def update_nfl_stats():
    """Try to update NFL stats from nflverse"""
    print("="*70)
    print("STEP 1: Updating NFL Player Stats from nflverse")
    print("="*70)

    try:
        print("Fetching 2025 season data (includes all available weeks)...")
        result = load_nfl_data_sync([2025])
        print(f"✅ Successfully loaded {result['total_records']} player stat records")
        print(f"✅ Successfully loaded {result['snap_records']} snap count records")
        return True
    except Exception as e:
        print(f"❌ Error loading NFL data: {e}")
        if "403" in str(e) or "Forbidden" in str(e):
            print("   (403 Forbidden - nflverse GitHub access restricted)")
        return False

def update_dk_salaries_api():
    """Try to update DK salaries via RapidAPI for weeks 9-10"""
    print("\n" + "="*70)
    print("STEP 2: Updating DraftKings Salaries via RapidAPI")
    print("="*70)

    weeks_to_fetch = [9, 10]
    success_count = 0

    for week in weeks_to_fetch:
        print(f"\nFetching Week {week}...")

        # Check if already exists
        existing = conn.execute(
            "SELECT COUNT(*) FROM draftkings_pricing WHERE season = 2025 AND week = ?",
            [week]
        ).fetchone()[0]

        if existing > 0:
            print(f"  Week {week} already has {existing} DK salary records - skipping")
            success_count += 1
            continue

        try:
            result = fetch_draftkings_salaries(2025, week)

            if result['success'] and result['data']:
                cached = cache_draftkings_pricing(result['data'], 2025, week)
                print(f"  ✅ Cached {cached} DK salary records for Week {week}")

                # Update weekly_stats
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
                    WHERE season = 2025 AND week = ?
                """, [week])

                success_count += 1
            else:
                error_msg = result.get('error', 'Unknown error')
                print(f"  ❌ Failed: {error_msg}")
        except Exception as e:
            print(f"  ❌ Error: {e}")
            if "403" in str(e) or "Forbidden" in str(e):
                print("     (403 Forbidden - RapidAPI access restricted)")

    return success_count > 0

def final_summary():
    """Show final database status"""
    print("\n" + "="*70)
    print("FINAL DATABASE STATUS")
    print("="*70)

    # Stats by week
    print("\nPlayer Stats by Week (2025):")
    stats_weeks = conn.execute("""
        SELECT week, COUNT(*) as count
        FROM weekly_stats
        WHERE season = 2025
        GROUP BY week
        ORDER BY week
    """).fetchall()

    for week, count in stats_weeks:
        print(f"  Week {week:2d}: {count:3d} players")

    # DK pricing by week
    print("\nDraftKings Salaries by Week (2025):")
    dk_weeks = conn.execute("""
        SELECT week, COUNT(*) as count
        FROM draftkings_pricing
        WHERE season = 2025
        GROUP BY week
        ORDER BY week
    """).fetchall()

    for week, count in dk_weeks:
        print(f"  Week {week:2d}: {count:3d} players")

    # Combined coverage
    print("\nCombined Coverage (Stats + DK Salaries):")
    combined = conn.execute("""
        SELECT
            week,
            COUNT(*) as total,
            COUNT(CASE WHEN dk_salary IS NOT NULL THEN 1 END) as with_salary,
            ROUND(COUNT(CASE WHEN dk_salary IS NOT NULL THEN 1 END) * 100.0 / COUNT(*), 1) as pct
        FROM weekly_stats
        WHERE season = 2025
        GROUP BY week
        ORDER BY week
    """).fetchall()

    for week, total, with_sal, pct in combined:
        status = "✅" if pct > 70 else "⚠️" if pct > 40 else "❌"
        print(f"  Week {week:2d}: {with_sal:3d}/{total:3d} players ({pct:5.1f}%) {status}")

    # Latest week
    if stats_weeks:
        latest_week = max([w for w, _ in stats_weeks])
        print(f"\n✅ Latest week with data: Week {latest_week}")

    print()

def main():
    print("NFL Hub Database Update - Target: Week 10")
    print(f"Started: {datetime.now()}")
    print()

    # Check current status
    check_current_status()

    # Step 1: Try to update NFL stats
    stats_updated = update_nfl_stats()

    # Step 2: Try to update DK salaries
    dk_updated = update_dk_salaries_api()

    # Show final summary
    final_summary()

    # Summary message
    print("="*70)
    if stats_updated and dk_updated:
        print("✅ SUCCESS: Database fully updated with latest data")
    elif stats_updated:
        print("⚠️  PARTIAL: Stats updated, but DK salaries may be incomplete")
    elif dk_updated:
        print("⚠️  PARTIAL: DK salaries updated, but stats may be incomplete")
    else:
        print("❌ FAILED: Unable to fetch new data (network restrictions)")
        print("   Current data remains unchanged")

    print("="*70)
    print(f"Completed: {datetime.now()}")

if __name__ == "__main__":
    main()
