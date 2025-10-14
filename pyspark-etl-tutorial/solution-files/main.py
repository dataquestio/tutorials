from pyspark.sql import SparkSession
import logging
import sys
import traceback
from datetime import datetime
from src.etl_pipeline import *
import os

def setup_logging():
    """Basic logging setup"""
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'logs/etl_run_{datetime.now().strftime("%Y%m%d")}.log'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

def main():
    """Main ETL pipeline"""

    logger = setup_logging()
    logger.info("Starting Grocery ETL Pipeline")

    # Track runtime
    start_time = datetime.now()

    try:
        # Initialize Spark
        spark = create_spark_session()
        logger.info("Spark session created")

        # Extract
        raw_df = extract_all_data(spark)
        logger.info(f"Extracted {raw_df.count()} raw records")

        # Transform
        clean_df = transform_orders(raw_df)
        logger.info(f"Transformed to {clean_df.count()} clean records")

        # Load
        output_path = "data/processed/orders"
        load_to_csv(spark, clean_df, output_path)

        # Sanity check
        sanity_check_data(spark, output_path)

        # Create summary
        summary = create_summary_report(clean_df)

        # Calculate runtime
        runtime = (datetime.now() - start_time).total_seconds()
        logger.info(f"Pipeline completed successfully in {runtime:.2f} seconds")

    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}")
        logger.debug(traceback.format_exc())
        raise

    finally:
        spark.stop()
        logger.info("Spark session closed")

if __name__ == "__main__":
    main()