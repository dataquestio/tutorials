from airflow.decorators import dag, task
from datetime import datetime, timedelta
import pandas as pd
import random
import os
import time
import requests
from bs4 import BeautifulSoup

default_args = {
    "owner": "Data Engineering Team",,
    "email": ["alerts@yourdomain.com"],
    "email_on_failure": True,
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
        Extracts Amazon Data Engineering book details such as Title, Author, Price, and Rating.
        Performs light cleaning to remove duplicates and incomplete records before saving.
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
        page = 1

        while page <= max_pages and len(books) < num_books:
            url = f"{base_url}&page={page}"

            try:
                response = requests.get(url, headers=headers, timeout=15)
            except requests.RequestException as e:
                print(f"Request failed: {e}")
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

                # Only add complete and new books
                if title_tag and price_tag:
                    title = title_tag.text.strip()

                    # Skip duplicates early
                    if title in seen_titles:
                        continue

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
            time.sleep(random.uniform(1.5, 3.0))  # Respectful delay

        # --- Final cleanup before saving ---
        df = pd.DataFrame(books)

        # Remove duplicates (just in case) and empty titles or prices
        df.dropna(subset=["Title", "Price"], inplace=True)
        df.drop_duplicates(subset="Title", inplace=True)

        # Create directory and save
        os.makedirs("/opt/airflow/tmp", exist_ok=True)
        raw_path = "/opt/airflow/tmp/amazon_books_raw.csv"
        df.to_csv(raw_path, index=False)

        print(f"[EXTRACT] Amazon book data successfully saved at {raw_path}")
        print(f"[EXTRACT] {len(df)} valid, unique records extracted across {page} pages.")

        # --- Push metadata to XCom for transform ---
        import json
        summary = {
            "rows": len(df),
            "columns": list(df.columns),
            "sample": df.head(3).to_dict('records'),
        }
        formatted_summary = json.dumps(summary, indent=2, ensure_ascii=False).replace('\xa0', ' ')

        if ti:
            ti.xcom_push(key='df_summary', value=formatted_summary)
            print("[XCOM] Pushed cleaned data summary to XCom.")

        print("\n Preview of Extracted Data:")
        print(df.head(5).to_string(index=False))

        return raw_path



    @task
    def transform_amazon_books(raw_file: str):
        if not os.path.exists(raw_file):
            raise FileNotFoundError(f"Raw file not found: {raw_file}")

        df = pd.read_csv(raw_file)
        print(f"[TRANSFORM] Loaded {len(df)} records from raw dataset.")

        # --- Price cleaning ---
        df["Price($)"] = (
            df["Price"]
            .str.replace("$", "", regex=False)
            .str.replace(",", "", regex=False)
            .str.strip()
        )
        df["Price($)"] = pd.to_numeric(df["Price($)"], errors="coerce")

        # --- Rating cleaning ---
        df["Rating"] = df["Rating"].str.extract(r"(\d+\.?\d*)").astype(float)

        # --- Validation: drop rows with invalid numeric values (optional) ---
        df.dropna(subset=["Price($)", "Rating"], how="all", inplace=True)

        # --- Drop original Price column ---
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
        """
        import mysql.connector
        import os
        import numpy as np

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

        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                Title VARCHAR(512),
                Author VARCHAR(255),
                `Price($)` DECIMAL(10,2),
                Rating DECIMAL(4,2)
            );
        """)


        # Insert each row safely
        for _, row in df.iterrows():
            cursor.execute(
                f"""
                INSERT INTO {table_name} (Title, Author, `Price($)`, Rating)
                VALUES (%s, %s, %s, %s)
                """,
                (row["Title"], row["Author"], row["Price($)"], row["Rating"])
            )


        conn.commit()
        conn.close()
        print(f"[LOAD] ✅ Data successfully loaded into MySQL table: {table_name}")



    # === Task dependencies ===
    raw_file = get_amazon_data_books()
    transformed_file = transform_amazon_books(raw_file)
    load_to_mysql(transformed_file)

dag = amazon_books_etl()