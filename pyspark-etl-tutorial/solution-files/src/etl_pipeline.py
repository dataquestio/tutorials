# src/etl_pipeline.py

from pyspark.sql import SparkSession
from pyspark.sql.types import *
from pyspark.sql.functions import *
import logging
from datetime import datetime

# Set up logger for this module
logger = logging.getLogger(__name__)

def create_spark_session():
    """Create a Spark session for our ETL job"""
    return SparkSession.builder \
        .appName("Grocery_Daily_ETL") \
        .config("spark.sql.adaptive.enabled", "true") \
        .getOrCreate()

def extract_sales_data(spark, input_path):
    """Read sales CSVs with all their real-world messiness"""

    logger.info(f"Reading sales data from {input_path}")

    # Define what we expect the schema to look like (without _corrupt_record)
    expected_schema = StructType([
        StructField("order_id", StringType(), True),
        StructField("customer_id", StringType(), True),
        StructField("product_name", StringType(), True),
        StructField("price", StringType(), True),
        StructField("quantity", StringType(), True),
        StructField("order_date", StringType(), True),
        StructField("region", StringType(), True)
    ])

    df = spark.read.csv(
        input_path,
        header=True,
        schema=expected_schema,
        mode="PERMISSIVE"  # Removed columnNameOfCorruptRecord
    )

    total_records = df.count()
    logger.info(f"Found {total_records} total records")

    return df

def extract_all_data(spark):
    """Combine data from multiple sources"""

    # Each system exports differently
    online_orders = extract_sales_data(spark, "data/raw/online_orders.csv")
    store_orders = extract_sales_data(spark, "data/raw/store_orders.csv")
    mobile_orders = extract_sales_data(spark, "data/raw/mobile_orders.csv")

    # Union them all together
    all_orders = online_orders.union(store_orders).union(mobile_orders)

    logger.info(f"Combined dataset has {all_orders.count()} orders")
    return all_orders

def clean_customer_id(df):
    """Standardize customer IDs (some are numbers, some are CUST_123 format)"""

    df_cleaned = df.withColumn(
        "customer_id_cleaned",
        when(col("customer_id").startswith("CUST_"), col("customer_id"))
        .when(col("customer_id").rlike("^[0-9]+$"), concat(lit("CUST_"), col("customer_id")))
        .otherwise(col("customer_id"))
    )

    return df_cleaned.drop("customer_id").withColumnRenamed("customer_id_cleaned", "customer_id")

def clean_price_column(df):
    """Fix the price column"""

    # Remove dollar signs, commas, and other nonsense
    df_cleaned = df.withColumn(
        "price_cleaned",
        regexp_replace(col("price"), "[^0-9.]", "")
    )

    # Convert to decimal, default to 0 if it fails
    df_final = df_cleaned.withColumn(
        "price_decimal",
        when(col("price_cleaned").isNotNull(),
             col("price_cleaned").cast(DoubleType()))
        .otherwise(0.0)
    )

    # Flag suspicious values for review
    df_flagged = df_final.withColumn(
        "price_quality_flag",
        when(col("price_decimal") == 0.0, "CHECK_ZERO_PRICE")
        .when(col("price_decimal") > 1000, "CHECK_HIGH_PRICE")
        .when(col("price_decimal") < 0, "CHECK_NEGATIVE_PRICE")
        .otherwise("OK")
    )

    bad_price_count = df_flagged.filter(col("price_quality_flag") != "OK").count()
    logger.warning(f"Found {bad_price_count} orders with suspicious prices")

    return df_flagged.drop("price", "price_cleaned")

def standardize_dates(df):
    """Parse dates in ISO format (yyyy-MM-dd)"""
    
    df_parsed = df.withColumn(
        "order_date_parsed",
        to_date(col("order_date"), "yyyy-MM-dd")
    )
    
    # Check how many we couldn't parse
    unparsed = df_parsed.filter(col("order_date_parsed").isNull()).count()
    if unparsed > 0:
        logger.warning(f"Could not parse {unparsed} dates")
    
    return df_parsed.drop("order_date")

def remove_test_data(df):
    """Remove test orders that somehow made it to production"""

    df_filtered = df.filter(
        ~(upper(col("customer_id")).contains("TEST") |
          upper(col("product_name")).contains("TEST") |
          col("customer_id").isNull() |
          col("order_id").isNull())
    )

    removed_count = df.count() - df_filtered.count()
    logger.info(f"Removed {removed_count} test/invalid orders")

    return df_filtered

def handle_duplicates(df):
    """Remove duplicate orders (usually from retries)"""

    df_deduped = df.dropDuplicates(["order_id"])

    duplicate_count = df.count() - df_deduped.count()
    if duplicate_count > 0:
        logger.info(f"Removed {duplicate_count} duplicate orders")

    return df_deduped

def transform_orders(df):
    """Apply all transformations in sequence"""

    logger.info("Starting data transformation...")

    # Clean each aspect of the data
    df = clean_customer_id(df)
    df = clean_price_column(df)
    df = standardize_dates(df)
    df = remove_test_data(df)
    df = handle_duplicates(df)

    # Cast quantity to integer
    df = df.withColumn(
        "quantity",
        when(col("quantity").isNotNull(), col("quantity").cast(IntegerType()))
        .otherwise(1)
    )

    # Add some useful calculated fields
    df = df.withColumn("total_amount", col("price_decimal") * col("quantity")) \
           .withColumn("processing_date", current_date()) \
           .withColumn("year", year(col("order_date_parsed"))) \
           .withColumn("month", month(col("order_date_parsed")))

    # Rename for clarity
    df = df.withColumnRenamed("order_date_parsed", "order_date") \
           .withColumnRenamed("price_decimal", "unit_price")

    logger.info(f"Transformation complete. Final record count: {df.count()}")

    return df

def load_to_csv(spark, df, output_path):
    """Save processed data for downstream use"""

    logger.info(f"Writing {df.count()} records to {output_path}")

    # Convert to pandas and write to avoid local machine issues
    pandas_df = df.toPandas()
    
    # Create output directory if needed
    import os
    os.makedirs(output_path, exist_ok=True)
    
    output_file = f"{output_path}/orders.csv"
    pandas_df.to_csv(output_file, index=False)

    logger.info(f"Successfully wrote {len(pandas_df)} records")
    logger.info(f"Output location: {output_file}")

    return len(pandas_df)

def sanity_check_data(spark, output_path):
    """Quick validation of processed data"""

    # Read the CSV file back
    output_file = f"{output_path}/orders.csv"
    df = spark.read.csv(output_file, header=True, inferSchema=True)
    df.createOrReplaceTempView("orders")

    # Run some quick validation queries
    total_count = spark.sql("SELECT COUNT(*) as total FROM orders").collect()[0]['total']
    logger.info(f"Sanity check - Total orders: {total_count}")

    # Check for any suspicious data that slipped through
    zero_price_count = spark.sql("""
        SELECT COUNT(*) as zero_prices
        FROM orders
        WHERE unit_price = 0
    """).collect()[0]['zero_prices']

    if zero_price_count > 0:
        logger.warning(f"Found {zero_price_count} orders with zero price")

    # Verify date ranges make sense
    date_range = spark.sql("""
        SELECT
            MIN(order_date) as earliest,
            MAX(order_date) as latest
        FROM orders
    """).collect()[0]

    logger.info(f"Date range: {date_range['earliest']} to {date_range['latest']}")

    return True

def create_summary_report(df):
    """Generate metrics about the ETL run"""

    summary = {
        "total_orders": df.count(),
        "unique_customers": df.select("customer_id").distinct().count(),
        "unique_products": df.select("product_name").distinct().count(),
        "total_revenue": df.agg(sum("total_amount")).collect()[0][0],
        "date_range": f"{df.agg(min('order_date')).collect()[0][0]} to {df.agg(max('order_date')).collect()[0][0]}",
        "regions": df.select("region").distinct().count()
    }

    logger.info("\n=== ETL Summary Report ===")
    for key, value in summary.items():
        logger.info(f"{key}: {value}")
    logger.info("========================\n")

    return summary