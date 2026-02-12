"""
Database initialization script for PostgreSQL on Railway
Converts SQLite data to PostgreSQL
"""
import os
import sqlite3
import psycopg2
from psycopg2.extras import execute_values

def init_postgres_db():
    """Initialize PostgreSQL database with data from SQLite"""
    DATABASE_URL = os.environ.get('DATABASE_URL')
    
    if not DATABASE_URL:
        print("No DATABASE_URL found - skipping PostgreSQL initialization")
        return
    
    print("🔄 Initializing PostgreSQL database...")
    
    try:
        # Connect to PostgreSQL
        pg_conn = psycopg2.connect(DATABASE_URL)
        pg_cursor = pg_conn.cursor()
        
        # Create tables
        print("📋 Creating tables...")
        
        # Providers table
        pg_cursor.execute("""
            CREATE TABLE IF NOT EXISTS providers (
                provider_id TEXT PRIMARY KEY,
                provider_name TEXT,
                specialty TEXT,
                license_status TEXT,
                tenure_years INTEGER,
                claims_per_month INTEGER,
                avg_claim_amount REAL,
                past_fraud_flags INTEGER
            )
        """)
        
        # Claim decisions table
        pg_cursor.execute("""
            CREATE TABLE IF NOT EXISTS claim_decisions (
                id SERIAL PRIMARY KEY,
                claim_id TEXT,
                risk_score REAL,
                decision TEXT,
                fraud_probability REAL,
                anomaly_score REAL,
                rule_violations TEXT,
                model_version TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        pg_conn.commit()
        print("✅ Tables created")
        
        # Check if providers table is empty
        pg_cursor.execute("SELECT COUNT(*) FROM providers")
        count = pg_cursor.fetchone()[0]
        
        if count == 0:
            print("📥 Loading data from SQLite...")
            # Connect to SQLite
            sqlite_conn = sqlite3.connect('data/fraud_detection.db')
            sqlite_cursor = sqlite_conn.cursor()
            
            # Copy providers
            sqlite_cursor.execute("SELECT * FROM providers")
            providers = sqlite_cursor.fetchall()
            
            if providers:
                execute_values(
                    pg_cursor,
                    """INSERT INTO providers 
                       (provider_id, provider_name, specialty, license_status, 
                        tenure_years, claims_per_month, avg_claim_amount, past_fraud_flags)
                       VALUES %s""",
                    providers
                )
                pg_conn.commit()
                print(f"✅ Loaded {len(providers)} providers")
            
            sqlite_conn.close()
        else:
            print(f"✅ Database already has {count} providers")
        
        pg_cursor.close()
        pg_conn.close()
        print("✅ PostgreSQL initialization complete")
        
    except Exception as e:
        print(f"❌ Error initializing PostgreSQL: {e}")
        print("⚠️  App will continue with SQLite")

if __name__ == "__main__":
    init_postgres_db()
