# Day 1 skeleton: base Python image for pipeline scripts.
# Ingestion/transformation dependencies and Airflow packaging are added in later days.
FROM python:3.11-slim

WORKDIR /app

# requirements.txt is a placeholder as of Day 1 (no ingestion/transformation code exists yet).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "--version"]
