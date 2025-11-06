
# Running and Managing Apache Airflow with Docker — Part One

This project contains the full solution for **Part One** of the *Running and Managing Apache Airflow with Docker* tutorial.

It walks through:
- Setting up Apache Airflow inside Docker using `docker-compose`
- Understanding the Airflow architecture
- Writing your first DAG using the **TaskFlow API**
- Implementing **Dynamic Task Mapping** for parallel processing


## Overview

In this hands-on project, you’ll learn how to:

1. Run Airflow locally using Docker Compose
2. Create and register your first DAG
3. Define tasks using the TaskFlow API
4. Use dynamic task mapping to process multiple markets in parallel


## Prerequisites

Before starting, ensure you have:

- [Docker Desktop](https://www.dataquest.io/blog/setting-up-your-data-engineering-lab-with-docker/)
- [Python 3.10+](https://www.python.org/downloads/)
- A code editor like VS Code


## Setup Instructions

### 1. Create the Project Folder

```bash
mkdir airflow-docker && cd airflow-docker
````

### 2. Download the Official Airflow Docker Compose File

```bash
curl -LfO 'https://airflow.apache.org/docs/apache-airflow/3.0.1/docker-compose.yaml'
```

### 3. Create Required Directories

```bash
mkdir -p ./dags ./logs ./plugins ./config
```

### 4. Initialize the Metadata Database

```bash
docker compose up airflow-init
```

### 5. Start Airflow

```bash
docker compose up -d
```

Access the Web UI at [http://localhost:8080](http://localhost:8080)
Default credentials:

* Username: `airflow`
* Password: `airflow`


## Working with DAGs

Place your DAG inside the `dags/` folder.
This solution’s DAG file is located under `src/our_first_dag.py`.

You can copy it into your project using:

```bash
cp src/our_first_dag.py dags/
```

Then, restart Airflow:

```bash
docker compose down -v
docker compose up -d
```

## DAG Overview

The DAG `daily_etl_pipeline_airflow3` demonstrates:

* **Extraction:** Simulating market data generation
* **Transformation:** Cleaning and analyzing data per market
* **Dynamic Task Mapping:** Running multiple markets in parallel (`us`, `europe`, `asia`, `africa`)

Each run produces transformed CSVs under `/opt/airflow/tmp/`.

## Project Flow

1. **Extract Market Data:**
   Generates synthetic stock data for several regions.
2. **Transform Market Data:**
   Sorts and identifies top-performing companies per region.
3. **Dynamic Task Mapping:**
   Uses `.expand()` to create one task per market dynamically.


## Visualizing the DAG

Once deployed, navigate to [http://localhost:8080](http://localhost:8080), open your DAG, and trigger a manual run.

In **Graph View**, you’ll see four parallel branches — one for each market region.


## Resetting the Environment

To cleanly stop and reset your containers:

```bash
docker compose down -v
```

Use this **only** if the environment is misconfigured.
Otherwise, prefer a soft stop:

```bash
docker compose down
```

