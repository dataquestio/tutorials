FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y postgresql-client && rm -rf /var/lib/apt/lists/*

COPY app.py .

RUN pip install psycopg2-binary

CMD ["python", "-u", "app.py"]