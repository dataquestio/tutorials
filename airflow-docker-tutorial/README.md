

# Amazon ETL with Apache Airflow + Docker

This repository contains the full project used in the **Amazon ETL with Apache Airflow and Docker** tutorial series.
It demonstrates a complete **end-to-end ETL workflow** using Apache Airflow, Docker, and MySQL, from local development all the way to cloud-like ready deployment patterns.

---

## Project Structure

* **`amazon-docker-tutorial/`** — The primary project folder containing the full Airflow setup used in Part One and Part Two of the tutorial.

You’ll find three main subdirectories:

* **`part-one/`** — The complete DAGs and configuration for the first part of the tutorial.
* **`part-two/`** — Git-based DAG syncing, CI validation, and lightweight deployment automation.
* **`amazon-etl/`** — The Amazon scraping + transformation code used for the real-world ETL example.

---

##  What’s Included

Inside `amazon-docker-tutorial/` you’ll find:

* **`docker-compose.yaml`** – A fully configured Airflow environment (api-server, scheduler, triggerer, DAG processor, metadata DB, logs).


The project walks through:

* Running Airflow inside Docker Compose
* Scraping real Amazon book data
* Transforming messy HTML output into clean analytics data
* Loading data into MySQL
* Syncing DAGs from GitHub using `git-sync`
* Lightweight CI for validating DAGs on every push

---

## How to Run the Project

Clone the repository:

```bash
git clone git@github.com:dataquestio/tutorials.git
cd amazon-docker-tutorial
```

Create required folders:

```bash
mkdir -p ./dags ./logs ./plugins ./config
```

Initialize Airflow:

```bash
docker compose up airflow-init
```

Start all services:

```bash
docker compose up -d
```

Access the Airflow UI:

```
http://localhost:8080
```

**Credentials:**

```
Username: airflow
Password: airflow
```

---

## Example DAGs

### `amazon_books_etl`

A real-world ETL pipeline that:

* **Extracts** book listings from Amazon (title, author, price, rating)
* **Transforms** the raw HTML data into numeric fields
* **Loads** the cleaned dataset into a MySQL table
* Runs automatically on a daily schedule

Files are saved to `/opt/airflow/tmp/` inside the container.

---

## Version Control & CI

You’ll also learn how to:

* Sync DAGs automatically from GitHub into Airflow using **git-sync**
* Validate DAG syntax on every push using a lightweight **GitHub Actions** workflow

These are production-like patterns for managing Airflow safely and collaboratively.

---

## Resetting the Environment

Stop all running containers:

```bash
docker compose down
```

Reset the environment completely (including the metadata database):

```bash
docker compose down -v
```

---

## Next Steps

* Explore the main DAG inside `dags/amazon_books_etl.py`
* Modify the extraction to use different Amazon categories or other sites
* Try connecting Airflow to cloud services (RDS, S3, ECS)
* Continue to the cloud deployment tutorial to run Airflow on **Amazon ECR (Fargate)**


