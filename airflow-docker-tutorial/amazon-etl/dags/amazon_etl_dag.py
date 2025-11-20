from airflow.decorators import dag, task
from datetime import datetime, timedelta
import pandas as pd
import random
import os
import time
import requests
from bs4 import BeautifulSoup

default_args = {
    "owner": "Data Engineering Team",
    "retries": 3,
    "retry_delay": timedelta(minutes=4),
}

@dag(
    dag_id="amazon_books_etl_pipeline",
    description="Automated ETL pipeline to fetch and clean Amazon Data Engineering book data into MySQL",
    schedule="@daily",
    start_date=datetime(2025, 11, 13),
    catchup=False,
    default_args=default_args,
    tags=["amazon", "etl", "airflow"],
)
def amazon_books_etl():

    @task
    def get_amazon_data_books(num_books=50, max_pages=10, ti=None):
        """
        Extracts Amazon Data Engineering book details such as Title, Author, Price, and Rating. Saves the raw extracted data locally and pushes it to XCom for downstream tasks.
        """
        headers = {
            "Referer": 'https://www.amazon.com/',
            "Sec-Ch-Ua": "Not_A Brand",
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": "macOS",
            'User-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36'
        }


        base_url = "https://www.amazon.com/s?k=data+engineering+books"
        books, seen_titles = [], set()
        page = 1  # start with page 1

        while page <= max_pages and len(books) < num_books:
            url = f"{base_url}&page={page}"

            try:
                response = requests.get(url, headers=headers, timeout=15)
            except requests.RequestException as e:
                print(f" Request failed: {e}")
                break

            if response.status_code != 200:
                print(f"Failed to retrieve page {page} (status {response.status_code})")
                break

            soup = BeautifulSoup(response.text, "html.parser")
            book_containers = soup.find_all("div", {"data-component-type": "s-impression-counter"})

            for book in book_containers:
                title_tag = book.select_one("h2 span")
                author_tag = book.select_one("a.a-size-base.a-link-normal")
                price_tag = book.select_one("span.a-price > span.a-offscreen")
                rating_tag = book.select_one("span.a-icon-alt")

                if title_tag and price_tag:
                    title = title_tag.text.strip()
                    if title not in seen_titles:
                        seen_titles.add(title)
                        books.append({
                            "Title": title,
                            "Author": author_tag.text.strip() if author_tag else "N/A",
                            "Price": price_tag.text.strip(),
                            "Rating": rating_tag.text.strip() if rating_tag else "N/A"
                        })
            if len(books) >= num_books:
                break

            page += 1
            time.sleep(random.uniform(1.5, 3.0))

        # Convert to DataFrame
        df = pd.DataFrame(books)
        df.drop_duplicates(subset="Title", inplace=True)

    
        # Create directory for raw data.
            # Note: This works here because everything runs in one container.
            # In real deployments, you'd use shared storage (e.g., S3/GCS) instead.
        os.makedirs("/opt/airflow/tmp", exist_ok=True)
        raw_path = "/opt/airflow/tmp/amazon_books_raw.csv"

        # Save the extracted dataset
        df.to_csv(raw_path, index=False)
        print(f"[EXTRACT] Amazon book data successfully saved at {raw_path}")

        # Push DataFrame path to XCom
        import json

        summary = {
            "rows": len(df),
            "columns": list(df.columns),
            "sample": df.head(3).to_dict('records'),
        }

        # Clean up non-breaking spaces and format neatly
        formatted_summary = json.dumps(summary, indent=2, ensure_ascii=False).replace('\xa0', ' ')


        if ti:
            ti.xcom_push(key='df_summary', value= formatted_summary)
            print("[XCOM] Pushed JSON summary to XCom.")

        # Optional preview
        print("\nPreview of Extracted Data:")
        print(df.head(5).to_string(index=False))

        return raw_path

    @task
    def transform_amazon_books(raw_file: str):
        """
        Standardizes the extracted Amazon book dataset for analysis.
        - Converts price strings (e.g., '$45.99') into numeric values
        - Extracts numeric ratings (e.g., '4.2' from '4.2 out of 5 stars')
        - Renames 'Price' to 'Price($)'
        - Handles missing or unexpected field formats safely
        - Performs light validation after numeric conversion
        """
        if not os.path.exists(raw_file):
            raise FileNotFoundError(f" Raw file not found: {raw_file}")

        df = pd.read_csv(raw_file)
        print(f"[TRANSFORM] Loaded {len(df)} records from raw dataset.")

        # --- Price cleaning (defensive) ---
        if "Price" in df.columns:
            df["Price($)"] = (
                df["Price"]
                .astype(str)                                   # prevents .str on NaN
                .str.replace("$", "", regex=False)
                .str.replace(",", "", regex=False)
                .str.extract(r"(\d+\.?\d*)")[0]                # safely extract numbers
            )
            df["Price($)"] = pd.to_numeric(df["Price($)"], errors="coerce")
        else:
            print("[TRANSFORM] Missing 'Price' column — filling with None.")
            df["Price($)"] = None

        # --- Rating cleaning (defensive) ---
        if "Rating" in df.columns:
            df["Rating"] = (
                df["Rating"]
                .astype(str)
                .str.extract(r"(\d+\.?\d*)")[0]
            )
            df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce")
        else:
            print("[TRANSFORM] Missing 'Rating' column — filling with None.")
            df["Rating"] = None

        # --- Validation: drop rows where BOTH fields failed (optional) ---
        df.dropna(subset=["Price($)", "Rating"], how="all", inplace=True)

        # --- Drop original Price column (if present) ---
        if "Price" in df.columns:
            df.drop(columns=["Price"], inplace=True)

        # --- Save cleaned dataset ---
        transformed_path = raw_file.replace("raw", "transformed")
        df.to_csv(transformed_path, index=False)

        print(f"[TRANSFORM] Cleaned data saved at {transformed_path}")
        print(f"[TRANSFORM] {len(df)} valid records after standardization.")
        print(f"[TRANSFORM] Sample cleaned data:\n{df.head(5).to_string(index=False)}")

        return transformed_path


    @task
    def load_to_mysql(transformed_file: str):
        """
        Loads the transformed Amazon book dataset into a MySQL table for analysis.
        Uses a truncate-and-load pattern to keep the table idempotent.
        """
        import mysql.connector
        import os
        import numpy as np

        # Note:
        # For production-ready projects, database credentials should never be hard-coded.
        # Airflow provides a built-in Connection system and can also integrate with
        # secret backends (AWS Secrets Manager, Vault, etc.).
        #
        # Example (production-ready project):
        #     hook = MySqlHook(mysql_conn_id="my_mysql_conn")
        #     conn = hook.get_conn()
        #
        # For this demo, we keep a simple local config:
        db_config = {
            "host": "host.docker.internal",
            "user": "airflow",
            "password": "airflow",
            "database": "airflow_db",
            "port": 3306
        }

        df = pd.read_csv(transformed_file)
        table_name = "amazon_books_data"

        # Replace NaN with None (important for MySQL compatibility)
        df = df.replace({np.nan: None})

        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Create table if it does not exist
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                Title VARCHAR(512),
                Author VARCHAR(255),
                `Price($)` DECIMAL(10,2),
                Rating DECIMAL(4,2)
            );
        """)
        
        # Truncate table for idempotency
        cursor.execute(f"TRUNCATE TABLE {table_name};")

        # Insert rows
        insert_query = f"""
            INSERT INTO {table_name} (Title, Author, `Price($)`, Rating)
            VALUES (%s, %s, %s, %s)
        """

        for _, row in df.iterrows():
            try:
                cursor.execute(
                    insert_query,
                    (row["Title"], row["Author"], row["Price($)"], row["Rating"])
                )
            except Exception as e:
                # For demo purposes we simply skip bad rows.
                # In real pipelines, you'd log or send them to a dead-letter table.
                print(f"[LOAD] Skipped corrupted row due to error: {e}")

        conn.commit()
        conn.close()

        print(f"[LOAD] Table '{table_name}' refreshed with {len(df)} rows.")

    # Task dependencies 
    raw_file = get_amazon_data_books()
    transformed_file = transform_amazon_books(raw_file)
    load_to_mysql(transformed_file)

dag = amazon_books_etl()
