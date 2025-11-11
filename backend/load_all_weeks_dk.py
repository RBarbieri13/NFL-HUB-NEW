#!/usr/bin/env python3
"""
Load ALL weeks of DraftKings salaries from Excel with proper ID generation
"""
import pandas as pd
import duckdb
from datetime import datetime, timezone
from pathlib import Path

# Database connection
ROOT_DIR = Path(__file__).parent
db_path = ROOT_DIR / "fantasy_football.db"
conn = duckdb.connect(str(db_path))

# Get the current max ID
max_id_result = conn.execute("SELECT COALESCE(MAX(id), 0) FROM draftkings_pricing").fetchone()
next_id = max_id_result[0] + 1

print(f"Starting ID: {next_id}\n")

# Read Excel file
df = pd.read_excel('dk_salaries.xlsx')
df['Week_Clean'] = pd.to_numeric(df['Week'], errors='coerce')
df = df[df['Week_Clean'].notna()]

print(f"Total rows in Excel: {len(df)}")
print(f"Weeks found: {sorted([int(w) for w in df['Week_Clean'].unique()])}\n")

# Process each week
total_inserted = 0

for week in sorted(df['Week_Clean'].unique()):
    week_int = int(week)
    week_df = df[df['Week_Clean'] == week].copy()

    # Check if week already has data
    existing_count = conn.execute(
        "SELECT COUNT(*) FROM draftkings_pricing WHERE season = 2025 AND week = ?",
        [week_int]
    ).fetchone()[0]

    if existing_count > 0:
        print(f"Week {week_int}: Already has {existing_count} records - SKIPPING")
        continue

    inserted = 0
    print(f"Week {week_int}: Processing {len(week_df)} rows...")

    for _, row in week_df.iterrows():
        try:
            name = str(row.get('NAME', '')).strip()
            team = str(row.get('TEAM', '')).strip().upper()
            position = str(row.get('POS', '')).strip().upper()
            salary_raw = row.get('$', 0)

            # Skip invalid data
            if pd.isna(name) or name == '' or name == 'NAME':
                continue
            if pd.isna(salary_raw) or salary_raw == '' or salary_raw == '$':
                continue
            if position not in ['QB', 'RB', 'WR', 'TE']:
                continue

            # Parse salary
            if isinstance(salary_raw, str):
                salary = int(salary_raw.replace('$', '').replace(',', '').strip())
            else:
                salary = int(salary_raw)

            if salary < 2000:
                continue

            # Insert with generated ID
            conn.execute("""
                INSERT INTO draftkings_pricing
                (id, player_name, team, position, season, week, salary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                next_id,
                name,
                team,
                position,
                2025,
                week_int,
                salary,
                datetime.now(timezone.utc)
            ))

            next_id += 1
            inserted += 1

        except Exception as e:
            # If duplicate (UNIQUE constraint on player_name+team+season+week), skip
            if 'UNIQUE' in str(e) or 'Constraint' in str(e):
                continue
            else:
                print(f"    Error: {e}")

    conn.commit()
    total_inserted += inserted
    print(f"  ✅ Inserted {inserted} players for Week {week_int}\n")

# Update weekly_stats with new DK salaries
print("="*60)
print("Updating weekly_stats with DK salaries...")
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
    WHERE season = 2025
      AND EXISTS (
        SELECT 1 FROM draftkings_pricing dp
        WHERE UPPER(TRIM(dp.player_name)) = UPPER(TRIM(weekly_stats.player_name))
          AND dp.team = weekly_stats.team
          AND dp.season = 2025
          AND dp.week = weekly_stats.week
      )
""")
print("✅ Updated weekly_stats\n")

# Final verification
print("="*60)
print("FINAL SUMMARY")
print("="*60)

print("\nDraftKings Pricing by Week:")
pricing = conn.execute("""
    SELECT week, COUNT(*) as count
    FROM draftkings_pricing
    WHERE season = 2025
    GROUP BY week
    ORDER BY week
""").fetchall()

for week, count in pricing:
    print(f"  Week {week}: {count} players")

print("\nCombined Coverage (Stats + Salaries):")
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
    print(f"  Week {week}: {with_sal:3d}/{total:3d} players with salaries ({pct}%)")

conn.close()
print(f"\n✅ Loaded {total_inserted} new DK salary records!")
