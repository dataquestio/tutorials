from airflow.decorators import dag, task
from datetime import datetime, timedelta
import pandas as pd
import random
import os

default_args = {
    "owner": "Brayan Opiyo",
    "retries": 3,
    "retry_delay": timedelta(minutes=1),
}

@dag(
    dag_id="daily_etl_pipeline_airflow3",
    description="ETL workflow demonstrating dynamic task mapping and assets",
    schedule="@daily",
    start_date=datetime(2025, 10, 22),
    catchup=False,
    default_args=default_args,
    tags=["airflow3", "etl"],
)
def daily_etl_pipeline():

    @task
    def extract_market_data(market: str):
        """Simulate extracting market data for a given region or market."""
        companies = ["Apple", "Amazon", "Google", "Microsoft", "Tesla", "Netflix"]
        records = []
        for company in companies:
            price = round(random.uniform(100, 1500), 2)
            change = round(random.uniform(-5, 5), 2)
            records.append({
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "market": market,
                "company": company,
                "price_usd": price,
                "daily_change_%": change,
            })

        df = pd.DataFrame(records)
        os.makedirs("/opt/airflow/tmp", exist_ok=True)
        raw_path = f"/opt/airflow/tmp/market_data_{market}.csv"
        df.to_csv(raw_path, index=False)
        print(f"[EXTRACT] Market data for {market} saved at {raw_path}")
        return raw_path

    @task
    def transform_market_data(raw_file: str):
        """Clean and analyze each regional dataset."""
        df = pd.read_csv(raw_file)
        df["price_usd"] = pd.to_numeric(df["price_usd"], errors="coerce")
        df["daily_change_%"] = pd.to_numeric(df["daily_change_%"], errors="coerce")
        df_sorted = df.sort_values(by="daily_change_%", ascending=False)

        top_gainers = df_sorted.head(3)
        top_losers = df_sorted.tail(3)

        transformed_path = raw_file.replace("market_data_", "transformed_")
        top_gainers.to_csv(transformed_path, index=False)
        print(f"[TRANSFORM] Transformed data saved at {transformed_path}")
        return transformed_path

    
    
    @task
    def load_to_mysql(transformed_file: str):
        """Load the transformed CSV data into a MySQL table."""
        import mysql.connector
        import os

        db_config = {
            "host": "host.docker.internal",  # enables Docker-to-local communication
            "user": "airflow",
            "password": "airflow",
            "database": "airflow_db",
            "port": 3306
        }

        df = pd.read_csv(transformed_file)

        # Derive the table name dynamically based on region
        table_name = f"transformed_market_data_{os.path.basename(transformed_file).split('_')[-1].replace('.csv', '')}"

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Create table if it doesn’t exist
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                timestamp VARCHAR(50),
                market VARCHAR(50),
                company VARCHAR(255),
                price_usd FLOAT,
                daily_change_percent FLOAT
            );
        """)

        # Insert records
        for _, row in df.iterrows():
            cursor.execute(
                f"""
                INSERT INTO {table_name} (timestamp, market, company, price_usd, daily_change_percent)
                VALUES (%s, %s, %s, %s, %s)
                """,
                tuple(row)
            )

        conn.commit()
        conn.close()
        print(f"[LOAD] Data successfully loaded into MySQL table: {table_name}")

    # Define markets to process dynamically
    markets = ["us", "europe", "asia", "africa"]

    from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator
		
    preview_mysql = SQLExecuteQueryOperator(
        task_id="preview_mysql_table",
        conn_id="local_mysql",
        sql="SELECT * FROM transformed_market_data_us LIMIT 5;",
        do_xcom_push=True,  # makes query results viewable in Airflow’s XCom tab
    )
		# Dynamically create and link tasks
    raw_files = extract_market_data.expand(market=markets)
    transformed_files = transform_market_data.expand(raw_file=raw_files)
    load_to_mysql.expand(transformed_file=transformed_files) >> preview_mysql
   
    # Dynamically create parallel tasks
    

dag = daily_etl_pipeline()
