# Kubernetes ETL Demo

This is a modified version of the ETL script from our Docker Compose tutorials, adapted to run continuously in Kubernetes for the **Kubernetes Services, Rollouts, and Namespages** tutorial on Dataquest.

## Included

* `app.py`: A simple Python ETL script that connects to a Postgres container and inserts a row into a table.
* `Dockerfile`: A single-stage Dockerfile that installs Python and runs the script.

## Build the image

```bash
docker build -t etl-app:v1 .
```

## Deploy to Kubernetes
Follow the instructions in the Kubernetes Services tutorial.