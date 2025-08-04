import psycopg2
import os

db_host = os.getenv("DB_HOST", "db")
print("Connected to DB:", db_host)
db_name = os.getenv("POSTGRES_DB", "products")
db_user = os.getenv("POSTGRES_USER", "postgres")
db_pass = os.getenv("POSTGRES_PASSWORD", "postgres")

new_vegetable = ("Parsnips", "Fresh", 2.42, 2.19)

try:
    conn = psycopg2.connect(
        host=db_host,
        dbname=db_name,
        user=db_user,
        password=db_pass
    )
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS vegetables (
            id SERIAL PRIMARY KEY,
            name TEXT,
            form TEXT,
            retail_price NUMERIC,
            cup_equivalent_price NUMERIC
        );
    """)

    cur.execute(
        """
        INSERT INTO vegetables (name, form, retail_price, cup_equivalent_price)
        VALUES (%s, %s, %s, %s);
        """,
        new_vegetable
    )

    conn.commit()
    cur.close()
    conn.close()
    print(f"ETL complete. 1 row inserted.")

except Exception as e:
    print("Error during ETL:", e)