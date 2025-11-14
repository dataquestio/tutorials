# main.py
from pyspark.sql import SparkSession
import logging
import sys
from datetime import datetime
from src.etl_pipeline import *

def setup_logging():
    """Configure logging for our pipeline"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

def main():
    """Main ETL pipeline - baseline version"""
    
    logger = setup_logging()
    logger.info("Starting Grocery ETL Pipeline - Baseline Version")
    
    start_time = datetime.now()

    spark = None  # Initialize to None for safe cleanup
    
    try:
        # Initialize Spark with minimal configuration
        spark = create_spark_session()
        logger.info("Spark session created")
        
        # Extract
        raw_df = extract_all_data(spark)
        logger.info("Extracted raw data from all sources")
        
        # Transform
        clean_df = transform_orders(raw_df)
        
        # Cache because we'll use this multiple times
        clean_df.cache()

        logger.info(f"Transformation complete: {clean_df.count()} clean records")

        # Create aggregated metrics for reporting
        metrics_df = create_metrics(clean_df)
        logger.info(f"Generated {metrics_df.count()} metric records")
        
        # Load to parquet
        output_path = "data/processed/orders"
        metrics_path = "data/processed/metrics"
        
        load_to_parquet(clean_df, output_path)
        load_to_parquet(metrics_df, metrics_path)

        # Generate summary report
        summary = create_summary_report(clean_df)

        # Clean up the cache when done
        clean_df.unpersist()
        
        runtime = (datetime.now() - start_time).total_seconds()
        logger.info(f"Pipeline completed in {runtime:.2f} seconds")
        
        # Keep Spark UI alive for exploration
        logger.info("Spark UI available at http://localhost:4040")
        logger.info("Press Enter when done exploring (Ctrl+C to skip)...")
        try:
            input()
        except (KeyboardInterrupt, EOFError):
            pass
        
    except Exception as e:
        logger.error(f"Pipeline failed: {str(e)}")
        raise

    finally:
        if spark is not None:
            spark.stop()
            logger.info("Spark session closed")

if __name__ == "__main__":
    main()