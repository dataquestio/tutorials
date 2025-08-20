# Continuous ETL: Python + Postgres ETL

This subdirectory contains the baseline ETL script for the **Kubernetes Services, Rollouts, and Namespages** tutorial on Dataquest.

## Included

* `app.py`: A simple Python ETL script that connects to a Postgres container and inserts a row into a table.
* `Dockerfile`: A single-stage Dockerfile that installs Python and runs the script.
* `docker-compose.yaml`: Defines two services—`db` (Postgres) and `app` (your ETL script).

## How to Run

To start the pipeline:

```
docker compose up --build
```

This will build the app container, start Postgres, and run the ETL script once.

## Notes

* Credentials are hardcoded in `docker-compose.yaml` for simplicity.
* This version is intentionally un-hardened.
* For best results, run this in a directory with Docker installed and no conflicting services on port 5432.