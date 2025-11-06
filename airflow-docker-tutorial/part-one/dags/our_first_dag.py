from airflow.decorators import dag, task
from datetime import datetime, timedelta
import pandas as pd
import random
import os

default_args = {
    "owner": "Your name",
    "retries": 3,
    "retry_delay": timedelta(minutes=1),
}

@dag(
    dag_id="daily_etl_pipeline_airflow3",
    description="ETL workflow demonstrating dynamic task mapping and assets",
    schedule="@daily",
    start_date=datetime(2025, 10, 29),
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
                "daily_change_percent": change,
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
        df["daily_change_percent"] = pd.to_numeric(df["daily_change_percent"], errors="coerce")
        df_sorted = df.sort_values(by="daily_change_percent", ascending=False)

        top_gainers = df_sorted.head(3)
        top_losers = df_sorted.tail(3)

        transformed_path = raw_file.replace("market_data_", "transformed_")
        top_gainers.to_csv(transformed_path, index=False)
        print(f"[TRANSFORM] Transformed data saved at {transformed_path}")
        return transformed_path

     # Define markets to process dynamically
    markets = ["us", "europe", "asia", "africa"]

    # Dynamically create parallel tasks
    raw_files = extract_market_data.expand(market=markets)
    transformed_files = transform_market_data.expand(raw_file=raw_files)

dag = daily_etl_pipeline()
