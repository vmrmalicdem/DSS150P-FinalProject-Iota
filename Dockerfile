# One image for everything that runs pipeline code: the Airflow webserver,
# the scheduler, and the one-off CLI runner (docker compose run pipeline ...).
# Airflow 2.10 is used because the DAG supports both Airflow 2 and 3 imports
# and 2.x needs only a webserver + scheduler.
FROM apache/airflow:2.10.5-python3.11

USER airflow
WORKDIR /opt/airflow/project

# Pipeline dependencies only; Airflow itself ships with the base image.
COPY --chown=airflow:root requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# The repository is bind-mounted at /opt/airflow/project by docker-compose.yml,
# so code edits (scripts/, dags/, sql/) apply without rebuilding the image.
# COPY keeps the image usable on its own (e.g. docker run without Compose).
COPY --chown=airflow:root . .

ENV PYTHONPATH=/opt/airflow/project/scripts \
    PIPELINE_SCRIPTS_DIR=/opt/airflow/project/scripts

CMD ["python", "--version"]
