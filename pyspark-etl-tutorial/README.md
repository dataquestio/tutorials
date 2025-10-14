# Building Your First ETL Pipeline with PySpark

Starter code and sample data for the Dataquest tutorial **"Building Your First Real ETL Pipeline with PySpark."**

You've learned PySpark basics, but actual data engineering is about building pipelines that run reliably with messy, real-world data. This tutorial walks you through building a complete ETL pipeline from scratch—no toy examples, just practical code that handles the chaos you'll encounter at work.

## What You'll Build

A production-ready ETL pipeline that:
- Reads messy CSV data from multiple sources (online orders, store orders, mobile orders)
- Handles real data quality issues: inconsistent formats, test data, duplicates
- Cleans and standardizes customer IDs, prices, and dates
- Outputs clean CSV files ready for analysis
- Includes logging, error handling, and data quality checks

## Setup

### Prerequisites
- Python 3.8+
- Java 11 or 17 (recommended for Spark)

### Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/dataquest/tutorials/pyspark-etl-tutorial.git
   cd pyspark-etl-tutorial
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Verify Spark is working:
   ```bash
   pyspark
   ```
   You should see the Spark shell start. Type `exit()` to quit.

## Project Structure

```
pyspark-etl-tutorial/
├── data/
│   └── raw/                    # Sample CSV files with realistic data issues
│       ├── online_orders.csv
│       ├── store_orders.csv
│       └── mobile_orders.csv
├── src/
│   └── (you'll create etl_pipeline.py here)
├── main.py                     # Skeleton orchestration code
└── requirements.txt
```

## Sample Data

The CSV files in `data/raw/` contain realistic data quality issues you'll fix:

- **Inconsistent customer IDs**: Some are numbers (`12345`), some have prefixes (`CUST_12345`)
- **Messy prices**: Mix of `$12.99` and `12.99` formats
- **Test data**: Records with `TEST` in various fields that need filtering
- **Duplicates**: Same order appearing multiple times
- **Inconsistent dates**: Different date formats across files

These are the exact issues you'll encounter in real production data.

## Tutorial

Follow the complete tutorial at: **[LINK TO TUTORIAL]**

The tutorial walks you through:
1. Setting up a professional ETL project structure
2. Building Extract, Transform, and Load functions
3. Handling data quality issues defensively
4. Adding logging, error handling, and validation
5. Running the complete pipeline with `spark-submit`

## Quick Start

After following the tutorial, run your completed pipeline:

```bash
spark-submit main.py
```

Successful output will be in `data/processed/orders/orders.csv` with a summary report in `logs/`.

## What You'll Learn

- **Professional ETL patterns**: Separate extract, transform, load functions
- **Defensive data reading**: Explicit schemas and error handling
- **Real-world transformations**: Cleaning messy strings, standardizing formats
- **Data quality**: Flagging suspicious values, removing test data
- **Production practices**: Logging, validation checks, summary reports

## Questions?

Open an issue in this repository or ask in the [Dataquest Community](https://community.dataquest.io/).