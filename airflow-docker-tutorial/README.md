
# Running and Managing Apache Airflow with Docker

This project contains the complete setup and example DAGs for the **Running and Managing Apache Airflow with Docker** tutorial series (Part One and Part Two).

It walks you through building an **end-to-end ETL pipeline** in Airflow — from local setup to database integration and version-controlled deployment.

---

## Overview

You’ll learn how to:

* Run **Apache Airflow** locally using **Docker Compose**
* Understand the **core components** of Airflow (Scheduler, Webserver, Workers, Triggerer, Metadata DB)
* Build and deploy your first DAG using the **TaskFlow API**
* Implement **Dynamic Task Mapping** to process multiple datasets in parallel
* Extend your pipeline with a **Load** step that writes data into **MySQL**
* Configure secure database connections using **Airflow Connections**
* Enable **Git-based DAG synchronization** with `git-sync`
* Automate DAG validation using **GitHub Actions (CI/CD)**

---

## Prerequisites

Before starting, make sure you have:

* [Docker Desktop](https://www.docker.com/products/docker-desktop/)
* [Python 3.10+](https://www.python.org/downloads/)
* A code editor such as **VS Code**

---

## Quick Start

### 1. Clone the Repository

```bash
git clone git@github.com:dataquestio/tutorials.git
cd airflow-docker-tutorial
```

> The `part-one` and `part-two` folders contain the complete DAGs for both tutorials.
> You’ll work primarily in the **airflow-docker-tutorial** directory.

### 2. Explore the Setup

Inside this directory, you’ll find the preconfigured `docker-compose.yaml` file that defines all Airflow services.

You’ll also create the following subfolders as you progress through the tutorial:

```bash
mkdir -p ./dags ./logs ./plugins ./config
```

### 3. Initialize and Start Airflow

```bash
docker compose up airflow-init
docker compose up -d
```

Access the Airflow Web UI at [http://localhost:8080](http://localhost:8080)

**Credentials**

```
Username: airflow
Password: airflow
```

---

## Example DAGs

### `daily_etl_pipeline_airflow3`

Demonstrates an end-to-end ETL flow with:

* **Extract:** Generate mock market data for multiple regions (`us`, `europe`, `asia`, `africa`)
* **Transform:** Clean and identify top gainers and losers per region
* **Load:** Insert transformed data into a local **MySQL** database
* **Dynamic Task Mapping:** Automatically parallelize extract/transform/load per region

Transformed files are saved under `/opt/airflow/tmp/`
and loaded into MySQL tables named:

```
transformed_market_data_us
transformed_market_data_europe
transformed_market_data_asia
transformed_market_data_africa
```

---

## Version Control & Automation

In Part Two, you’ll integrate:

* **Git-Sync:** Automatically sync DAGs from your GitHub repo into Airflow
* **GitHub Actions:** Validate DAG syntax before deployment

This mirrors how production data teams manage and deploy Airflow pipelines safely and collaboratively.

---

## Resetting the Environment

To stop containers cleanly:

```bash
docker compose down
```

To remove all data and start fresh (including connections and logs):

```bash
docker compose down -v
```

---

## Next Steps

* Explore `dags/our_first_dag.py` to see how tasks are defined with the TaskFlow API
* Modify the DAG to connect to your own data sources or cloud-hosted MySQL
* Continue to the next tutorial to add API extraction, alerts, and full CI/CD deployment

---

