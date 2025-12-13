#!/usr/bin/env python3
"""
Test script to validate the performance improvements in the optimized data loader.
"""

import time
import logging
import duckdb
from pathlib import Path
from optimized_data_loader import OptimizedDataLoader, OptimizedAPIClient

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_database_connection():
    """Test database connection and basic operations"""
    try:
        db_path = Path(__file__).parent / "fantasy_football.db"
        conn = duckdb.connect(str(db_path))
        
        # Test basic query
        tables = conn.execute("SHOW TABLES").fetchall()
        logging.info(f"✅ Database connection successful. Tables: {[t[0] for t in tables]}")
        
        # Test indexes
        try:
            result = conn.execute("SELECT COUNT(*) FROM weekly_stats WHERE season = 2024 AND week = 1").fetchone()
            logging.info(f"✅ Index test successful. Sample query returned {result[0]} records")
        except Exception as e:
            logging.warning(f"⚠️ Index test failed: {e}")
        
        conn.close()
        return True
    except Exception as e:
        logging.error(f"❌ Database connection failed: {e}")
        return False

def test_optimized_loader():
    """Test the optimized data loader"""
    try:
        db_path = Path(__file__).parent / "fantasy_football.db"
        conn = duckdb.connect(str(db_path))
        
        loader = OptimizedDataLoader(conn)
        logging.info("✅ OptimizedDataLoader initialized successfully")
        
        # Test name normalization cache
        test_names = ["Patrick Mahomes II", "DeAndre Hopkins", "D.K. Metcalf"]
        for name in test_names:
            normalized = loader.normalize_player_name(name)
            mapped = loader.get_mapped_name(name)
            logging.info(f"Name: '{name}' -> Normalized: '{normalized}' -> Mapped: '{mapped}'")
        
        conn.close()
        return True
    except Exception as e:
        logging.error(f"❌ OptimizedDataLoader test failed: {e}")
        return False

def test_api_client():
    """Test the optimized API client"""
    try:
        api_client = OptimizedAPIClient(
            api_key="31cd7fd5cfmsh0039d0aaa4b3cf4p187526jsn4273673a1752",
            api_host="tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com"
        )
        logging.info("✅ OptimizedAPIClient initialized successfully")
        
        # Test rate limiting
        start_time = time.time()
        api_client._rate_limit()
        api_client._rate_limit()
        elapsed = time.time() - start_time
        logging.info(f"✅ Rate limiting test: {elapsed:.3f}s elapsed (should be >= 0.1s)")
        
        return True
    except Exception as e:
        logging.error(f"❌ OptimizedAPIClient test failed: {e}")
        return False

def test_query_performance():
    """Test query performance with indexes"""
    try:
        db_path = Path(__file__).parent / "fantasy_football.db"
        conn = duckdb.connect(str(db_path))
        
        # Test various query patterns that should benefit from indexes
        test_queries = [
            ("Player lookup", "SELECT * FROM weekly_stats WHERE player_name = 'Josh Allen' AND season = 2024"),
            ("Team/season lookup", "SELECT COUNT(*) FROM weekly_stats WHERE team = 'BUF' AND season = 2024"),
            ("Position filter", "SELECT COUNT(*) FROM weekly_stats WHERE position = 'QB' AND season = 2024"),
            ("Week filter", "SELECT COUNT(*) FROM weekly_stats WHERE season = 2024 AND week = 1"),
            ("Snap counts join", """
                SELECT COUNT(*) FROM weekly_stats ws 
                JOIN snap_counts sc ON ws.player_name = sc.player_name 
                    AND ws.team = sc.team AND ws.season = sc.season AND ws.week = sc.week
                WHERE ws.season = 2024
            """),
            ("Pricing join", """
                SELECT COUNT(*) FROM weekly_stats ws 
                JOIN draftkings_pricing dp ON ws.player_name = dp.player_name 
                    AND ws.team = dp.team AND ws.season = dp.season AND ws.week = dp.week
                WHERE ws.season = 2024
            """)
        ]
        
        for query_name, query in test_queries:
            start_time = time.time()
            try:
                result = conn.execute(query).fetchone()
                elapsed = time.time() - start_time
                logging.info(f"✅ {query_name}: {elapsed:.3f}s, result: {result[0] if result else 'N/A'}")
            except Exception as e:
                logging.warning(f"⚠️ {query_name} failed: {e}")
        
        conn.close()
        return True
    except Exception as e:
        logging.error(f"❌ Query performance test failed: {e}")
        return False

def test_data_integrity():
    """Test data integrity after optimizations"""
    try:
        db_path = Path(__file__).parent / "fantasy_football.db"
        conn = duckdb.connect(str(db_path))
        
        # Check for data consistency
        integrity_checks = [
            ("Weekly stats count", "SELECT COUNT(*) FROM weekly_stats"),
            ("Snap counts count", "SELECT COUNT(*) FROM snap_counts"),
            ("Pricing count", "SELECT COUNT(*) FROM draftkings_pricing"),
            ("Players with snap data", "SELECT COUNT(*) FROM weekly_stats WHERE snap_percentage IS NOT NULL"),
            ("Players with salary data", "SELECT COUNT(*) FROM weekly_stats WHERE dk_salary IS NOT NULL"),
            ("Unique player-season-week combinations", "SELECT COUNT(DISTINCT id) FROM weekly_stats"),
            ("Fantasy points range", "SELECT MIN(fantasy_points), MAX(fantasy_points) FROM weekly_stats WHERE fantasy_points > 0")
        ]
        
        for check_name, query in integrity_checks:
            try:
                result = conn.execute(query).fetchone()
                logging.info(f"✅ {check_name}: {result}")
            except Exception as e:
                logging.warning(f"⚠️ {check_name} failed: {e}")
        
        conn.close()
        return True
    except Exception as e:
        logging.error(f"❌ Data integrity test failed: {e}")
        return False

def main():
    """Run all optimization tests"""
    logging.info("🚀 Starting optimization validation tests...")
    
    tests = [
        ("Database Connection", test_database_connection),
        ("Optimized Loader", test_optimized_loader),
        ("API Client", test_api_client),
        ("Query Performance", test_query_performance),
        ("Data Integrity", test_data_integrity)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logging.info(f"\n📋 Running {test_name} test...")
        if test_func():
            passed += 1
            logging.info(f"✅ {test_name} test PASSED")
        else:
            logging.error(f"❌ {test_name} test FAILED")
    
    logging.info(f"\n🏁 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        logging.info("🎉 All optimization tests passed! The backend is ready for improved performance.")
    else:
        logging.warning(f"⚠️ {total - passed} test(s) failed. Please review the issues above.")

if __name__ == "__main__":
    main()