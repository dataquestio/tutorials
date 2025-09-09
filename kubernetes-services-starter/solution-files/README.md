# Kubernetes Configuration and Production - Solution Files

These are the solution files for the **Kubernetes Configuration and Production** tutorial.

## What's Included

**`app.py`** - Updated ETL script with heartbeat mechanism for liveness probes

**`Dockerfile`** - Updated container definition that includes PostgreSQL client tools for health checks

**`etl-deployment-with-env.yaml`** - Deployment with hardcoded environment variables (used in early tutorial steps)

**`etl-deployment-with-envFrom.yaml`** - Production-ready deployment using ConfigMaps and Secrets for external configuration

## File Progression

The tutorial builds up your deployment in stages. Start with `etl-deployment-with-en.yaml` when you first add health checks and resource limits. Switch to `etl-deployment-with-envFrom.yaml` when you reach the ConfigMaps and Secrets section.