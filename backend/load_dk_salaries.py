#!/usr/bin/env python3
"""
Script to load DraftKings salary data from Excel file into database
"""
import pandas as pd
import duckdb
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Database connection
ROOT_DIR = Path(__file__).parent
db_path = ROOT_DIR / "fantasy_football.db"
conn = duckdb.connect(str(db_path))

# Read Excel file
excel_file = ROOT_DIR / "dk_salaries.xlsx"
print(f"Reading Excel file: {excel_file}")

# Read all sheets
xl = pd.ExcelFile(excel_file)
print(f"Sheet names: {xl.sheet_names}")

# Process each sheet (assuming each sheet is a week or all data is in one sheet)
for sheet_name in xl.sheet_names:
    print(f"\nProcessing sheet: {sheet_name}")
    df = pd.read_excel(excel_file, sheet_name=sheet_name)
    
    print(f"Columns: {df.columns.tolist()}")
    print(f"Shape: {df.shape}")
    print(f"First 5 rows:")
    print(df.head())
    
    # Check if there's a WEEK column
    if 'WEEK' in df.columns:
        print(f"Unique weeks in data: {df['WEEK'].unique()}")
    
    # Parse and load data
    inserted = 0
    updated = 0
    skipped = 0
    
    for idx, row in df.iterrows():
        try:
            # Extract data - adjust column names based on actual structure
            week = row.get('WEEK', 1)  # Default to week 1 if not specified
            name = row.get('NAME', row.get('name', row.get('Player', '')))
            team = row.get('TEAM', row.get('team', row.get('Team', '')))
            position = row.get('POS', row.get('pos', row.get('Position', '')))
            salary_raw = row.get('$', row.get('Salary', row.get('salary', 0)))
            
            # Clean up data
            if pd.isna(name) or name == '':
                skipped += 1
                continue
                
            name = str(name).strip()
            team = str(team).strip().upper() if not pd.isna(team) else 'UNK'
            position = str(position).strip().upper() if not pd.isna(position) else 'UNK'
            
            # Parse salary
            if pd.isna(salary_raw):
                salary = 0
            elif isinstance(salary_raw, str):
                salary = int(salary_raw.replace('$', '').replace(',', '').strip())
            else:
                salary = int(salary_raw)
            
            if salary == 0 or salary < 2000:
                skipped += 1
                continue
            
            # Only QB, RB, WR, TE
            if position not in ['QB', 'RB', 'WR', 'TE']:
                skipped += 1
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
                inserted += 1
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
                    updated += 1
                else:
                    print(f"Error on row {idx}: {e}")
                    skipped += 1
                    
        except Exception as e:
            print(f"Error processing row {idx}: {e}")
            skipped += 1
    
    conn.commit()
    print(f"\nSheet '{sheet_name}' processed:")
    print(f"  Inserted: {inserted}")
    print(f"  Updated: {updated}")
    print(f"  Skipped: {skipped}")

# Verify data loaded
print("\n" + "="*60)
print("VERIFICATION - Data loaded by week:")
result = conn.execute("""
    SELECT week, COUNT(*) as player_count, COUNT(DISTINCT position) as positions
    FROM draftkings_pricing
    WHERE season = 2025
    GROUP BY week
    ORDER BY week
""").fetchall()

for row in result:
    print(f"Week {row[0]}: {row[1]} players, {row[2]} positions")

print("\n" + "="*60)
print("Sample data:")
sample = conn.execute("""
    SELECT week, player_name, team, position, salary
    FROM draftkings_pricing
    WHERE season = 2025
    ORDER BY week, salary DESC
    LIMIT 20
""").fetchall()

for row in sample:
    print(f"Week {row[0]}: {row[1]} ({row[2]} {row[3]}) - ${row[4]}")

conn.close()
print("\n✅ DraftKings pricing data loaded successfully!")
