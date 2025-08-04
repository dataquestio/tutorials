FROM python:3.10-slim

WORKDIR /app

COPY app.py .

RUN pip install psycopg2-binary

CMD ["python", "app.py"]