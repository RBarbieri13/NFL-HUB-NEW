#!/usr/bin/env python3
"""
Script to update NFL Hub database with the latest week's data
"""
import sys
import asyncio
from datetime import datetime
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Import functions from server.py
from server import (
    load_nfl_data_sync,
    scrape_draftkings_salaries_from_fantasypros,
    conn,
    logging
)

def main():
    """Main function to update all data"""
    print("=" * 60)
    print("NFL Hub Data Update - Latest Week")
    print("=" * 60)
    print(f"Started at: {datetime.now()}")
    print()

    # Step 1: Load NFL player stats and snap counts
    print("Step 1: Loading NFL player stats and snap counts from nflverse...")
    print("-" * 60)
    try:
        result = load_nfl_data_sync([2024, 2025])
        print(f"✅ Successfully loaded {result['total_records']} player stat records")
        print(f"✅ Successfully loaded {result['snap_records']} snap count records")
    except Exception as e:
        print(f"❌ Error loading NFL data: {e}")
        import traceback
        traceback.print_exc()

    print()

    # Step 2: Scrape DraftKings salaries
    print("Step 2: Scraping latest DraftKings salaries from FantasyPros...")
    print("-" * 60)
    try:
        # Run async function
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(scrape_draftkings_salaries_from_fantasypros())
        loop.close()

        if result.get('success'):
            print(f"✅ Successfully scraped DraftKings salaries")
            print(f"   Season: {result.get('season')}, Week: {result.get('week')}")
            print(f"   Inserted: {result.get('inserted', 0)}, Updated: {result.get('updated', 0)}")
        else:
            print(f"⚠️  Scraping completed with message: {result.get('message')}")
    except Exception as e:
        print(f"❌ Error scraping DraftKings salaries: {e}")
        import traceback
        traceback.print_exc()

    print()

    # Step 3: Verify data
    print("Step 3: Verifying latest data in database...")
    print("-" * 60)
    try:
        # Check latest week in weekly_stats
        latest_week_result = conn.execute("""
            SELECT season, MAX(week) as latest_week, COUNT(*) as record_count
            FROM weekly_stats
            WHERE season = 2025
            GROUP BY season
        """).fetchone()

        if latest_week_result:
            print(f"📊 Latest data in weekly_stats:")
            print(f"   Season: {latest_week_result[0]}")
            print(f"   Latest Week: {latest_week_result[1]}")
            print(f"   Total Records: {latest_week_result[2]}")

        # Check DraftKings pricing
        dk_pricing_result = conn.execute("""
            SELECT season, week, COUNT(*) as player_count
            FROM draftkings_pricing
            WHERE season = 2025
            GROUP BY season, week
            ORDER BY week DESC
            LIMIT 1
        """).fetchone()

        if dk_pricing_result:
            print(f"💰 Latest DraftKings pricing:")
            print(f"   Season: {dk_pricing_result[0]}")
            print(f"   Week: {dk_pricing_result[1]}")
            print(f"   Players with salaries: {dk_pricing_result[2]}")

        # Check players with both stats and salaries for latest week
        combined_result = conn.execute("""
            SELECT COUNT(*) as count
            FROM weekly_stats ws
            WHERE ws.season = 2025
              AND ws.week = (SELECT MAX(week) FROM weekly_stats WHERE season = 2025)
              AND ws.dk_salary IS NOT NULL
        """).fetchone()

        if combined_result:
            print(f"🔗 Players with both stats AND DK salaries (latest week): {combined_result[0]}")

    except Exception as e:
        print(f"❌ Error verifying data: {e}")
        import traceback
        traceback.print_exc()

    print()
    print("=" * 60)
    print(f"Update completed at: {datetime.now()}")
    print("=" * 60)

if __name__ == "__main__":
    main()
