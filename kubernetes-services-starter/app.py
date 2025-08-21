import os
import time
import psycopg2
import sys
import traceback

DB_HOST = os.getenv("DB_HOST", "postgres")   # default to the Service name you'll use
DB_NAME = os.getenv("DB_NAME", "pipeline")
DB_USER = os.getenv("DB_USER", "etl")
DB_PASS = os.getenv("DB_PASSWORD", "mysecretpassword")
DB_PORT = int(os.getenv("DB_PORT", "5432"))

def log(msg):
    print(msg, flush=True)

log(f"ETL app starting - will connect to {DB_HOST}:{DB_PORT} db={DB_NAME} user={DB_USER}")

def run_etl():
    try:
        log("Connecting to Postgres...")
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
            connect_timeout=3  # fail fast so we print errors regularly
        )
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vegetables (
                id SERIAL PRIMARY KEY,
                name TEXT,
                form TEXT,
                retail_price NUMERIC,
                cup_equivalent_price NUMERIC,
                inserted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            INSERT INTO vegetables (name, form, retail_price, cup_equivalent_price)
            VALUES (%s, %s, %s, %s);
        """, ("Parsnips", "Fresh", 2.42, 2.19))
        conn.commit()
        cur.close()
        conn.close()
        log("ETL cycle complete - 1 row inserted")
    except Exception as e:
        # print full traceback so you see the real failure in kubectl logs
        log(f"Error during ETL: {e}")
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()

if __name__ == "__main__":
    while True:
        run_etl()
        log("Sleeping for 30 seconds...")
        time.sleep(30)
