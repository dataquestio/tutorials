# src/etl_pipeline.py
from pyspark.sql import SparkSession
from pyspark.sql.types import *
from pyspark.sql.functions import (
    col, when, concat, lit, regexp_replace, coalesce, to_date, 
    upper, current_date, year, month, sum, avg, count, min, max,
    countDistinct
)
import logging

logger = logging.getLogger(__name__)

def create_spark_session():
    """Create Spark session with basic configuration"""
    return SparkSession.builder \
        .appName("Grocery_ETL_Baseline") \
        .config("spark.sql.adaptive.enabled", "false") \
        .getOrCreate()

def extract_sales_data(spark, input_path):
    """Read CSV files with explicit schema"""
    
    logger.info(f"Reading sales data from {input_path}")
    
    schema = StructType([
        StructField("order_id", StringType(), True),
        StructField("customer_id", StringType(), True),
        StructField("product_name", StringType(), True),
        StructField("price", StringType(), True),
        StructField("quantity", StringType(), True),
        StructField("order_date", StringType(), True),
        StructField("region", StringType(), True)
    ])
    
    df = spark.read.csv(input_path, header=True, schema=schema)
    
    # No count here - just return the DataFrame
    return df

def extract_all_data(spark):
    """Combine data from multiple sources"""
    
    online_orders = extract_sales_data(spark, "data/raw/online_orders.csv")
    store_orders = extract_sales_data(spark, "data/raw/store_orders.csv")
    mobile_orders = extract_sales_data(spark, "data/raw/mobile_orders.csv")
    
    all_orders = online_orders.unionByName(store_orders).unionByName(mobile_orders)
    
    logger.info("Combined data from all sources")
    return all_orders

def clean_customer_id(df):
    """Standardize customer IDs"""
    return df.withColumn(
        "customer_id_cleaned",
        when(col("customer_id").startswith("CUST_"), col("customer_id"))
        .when(col("customer_id").rlike("^[0-9]+$"), 
              concat(lit("CUST_"), col("customer_id")))
        .otherwise(col("customer_id"))
    ).drop("customer_id").withColumnRenamed("customer_id_cleaned", "customer_id")

def clean_price_column(df):
    """Clean and convert prices"""
    df_cleaned = df.withColumn(
        "price_cleaned",
        regexp_replace(col("price"), r"[^0-9.\-]", "")
    )
    
    df_final = df_cleaned.withColumn(
        "price_decimal",
        when(col("price_cleaned").isNotNull(),
             col("price_cleaned").cast(DoubleType()))
        .otherwise(0.0)
    )
    
    return df_final.drop("price", "price_cleaned") \
                   .withColumnRenamed("price_decimal", "unit_price")

def standardize_dates(df):
    """Parse dates in multiple formats"""
    df_parsed = df.withColumn(
        "order_date_parsed",
        coalesce(
            to_date(col("order_date"), "yyyy-MM-dd"),
            to_date(col("order_date"), "MM/dd/yyyy"),
            to_date(col("order_date"), "dd-MM-yyyy")
        )
    )
    
    return df_parsed.drop("order_date") \
                    .withColumnRenamed("order_date_parsed", "order_date")

def remove_test_data(df):
    """Filter out test records"""
    df_filtered = df.filter(
        ~(upper(col("customer_id")).contains("TEST") |
          upper(col("product_name")).contains("TEST") |
          col("customer_id").isNull() |
          col("order_id").isNull())
    )
    
    logger.info("Removed test and invalid orders")
    return df_filtered

def handle_duplicates(df):
    """Remove duplicate orders"""
    df_deduped = df.dropDuplicates(["order_id"])
    
    logger.info("Removed duplicate orders")
    return df_deduped

def transform_orders(df):
    """Apply all transformations in sequence"""
    
    logger.info("Starting data transformation...")
    
    # Filter first - remove data we won't use
    df = remove_test_data(df)
    df = handle_duplicates(df)
    
    # Then do expensive transformations on clean data only
    df = clean_customer_id(df)
    df = clean_price_column(df)
    df = standardize_dates(df)
    
    # Cast quantity and add calculated fields
    df = df.withColumn(
        "quantity",
        when(col("quantity").isNotNull(), col("quantity").cast(IntegerType()))
        .otherwise(1)
    )
    
    df = df.withColumn("total_amount", col("unit_price") * col("quantity")) \
           .withColumn("processing_date", current_date()) \
           .withColumn("year", year(col("order_date"))) \
           .withColumn("month", month(col("order_date")))
    
    logger.info("Transformation complete")
    
    return df

def create_metrics(df):
    """Generate aggregated metrics for each product"""
    
    # INEFFICIENCY #5: This creates a separate aggregation pipeline
    # that we'll need to join back with the main data later
    # Also, no caching means we'll recompute df multiple times
    
    logger.info("Creating product metrics...")
    
    # Product-level metrics
    product_metrics = df.groupBy("product_name", "region").agg(
        count("*").alias("order_count"),
        sum("total_amount").alias("total_revenue"),
        avg("unit_price").alias("avg_price"),
        sum("quantity").alias("total_quantity")
    )
    
    # INEFFICIENCY #6: More counting operations
    logger.info(f"Generated metrics for {product_metrics.count()} product-region combinations")
    
    return product_metrics

def load_to_parquet(df, output_path):
    """Save to parquet with proper partitioning"""
    
    logger.info(f"Writing data to {output_path}")
    
    # Coalesce to 1 partition before writing
    # This creates a single output file instead of 200 tiny ones
    df.coalesce(1) \
      .write \
      .mode("overwrite") \
      .parquet(output_path)
    
    logger.info(f"Successfully wrote data to {output_path}")

def create_summary_report(df):
    """Generate summary statistics efficiently"""
    
    logger.info("Generating summary report...")
    
    # Compute everything in a single aggregation
    stats = df.agg(
        count("*").alias("total_orders"),
        countDistinct("customer_id").alias("unique_customers"),
        countDistinct("product_name").alias("unique_products"),
        sum("total_amount").alias("total_revenue"),
        min("order_date").alias("earliest_date"),
        max("order_date").alias("latest_date"),
        countDistinct("region").alias("regions")
    ).collect()[0]
    
    summary = {
        "total_orders": stats["total_orders"],
        "unique_customers": stats["unique_customers"],
        "unique_products": stats["unique_products"],
        "total_revenue": stats["total_revenue"],
        "date_range": f"{stats['earliest_date']} to {stats['latest_date']}",
        "regions": stats["regions"]
    }
    
    logger.info("\n=== ETL Summary Report ===")
    for key, value in summary.items():
        logger.info(f"{key}: {value}")
    logger.info("========================\n")
    
    return summary