# Technical Report: Short-Video Risk Pipeline

**Topic:** Addictive Usage & Well-being Risk Detection

## 1. Problem and Objectives
Short-video platforms can inadvertently foster compulsive usage patterns, posing mental health risks, particularly for students and young adults. The objective of this project is to build an automated data engineering pipeline that processes raw interaction logs to detect these risky behavioral signatures. 

Instead of a one-off analysis, we implemented a robust pipeline to transform millions of raw interaction events into daily, per-user profiles. These profiles quantify binge-watching patterns (e.g., late-night usage spikes, long unbroken sessions, high frequencies of "hate" reactions signaling continued compulsive scrolling despite negative emotions). The curated dataset serves as the foundation for future early-warning systems or "digital wellbeing" nudges.

## 2. Data Sources
We sourced data from the Tsinghua FIB Lab `ShortVideo_dataset`, supplemented by a programmatic REST API ingestion:
1. **`interaction_sampled.csv` (CSV):** 794,053 rows of raw user-video interaction logs.
2. **`categories_cn_en.csv` (CSV):** 826 rows mapping category IDs to English and Chinese labels.
3. **`asr_en/*.txt` (TXT):** 10 transcript files demonstrating multi-format ingestion capabilities.
4. **Programmatic Metadata (JSON):** Retrieved via REST API during ingestion to meet source diversity requirements and provide JSON-format handling.

## 3. Architecture and Implementation
The architecture follows a classic layered Data Engineering approach (Raw -> Staging -> Curated), orchestrated by Apache Airflow and containerized via Docker. (See `docs/architecture.md` and `docs/data-flow.md` for visual diagrams).

*   **Ingestion:** Python scripts fetch the CSV/TXT files and the REST API JSON, writing them immutably to the Raw layer, partitioned by `p_date`.
*   **Staging:** We deduplicate exact rows, collapse tag-level fan-out, cast data types, and resolve cross-partition ownership anomalies (keeping events in their earliest partition).
*   **Curation:** We derive critical behavioral features: `watch_ratio`, `is_rewatch_flagged`, `late_night_share`, `max_session_seconds`, and `hate_rate`.

## 4. Data Model and Storage
We implemented PostgreSQL for structured analytical storage (see `docs/erd.md`).
*   **Dimensions (users, videos, categories, video_categories):** Loaded using an UPSERT strategy.
*   **Facts (interactions_curated, daily_user_features):** Partitioned by `p_date` and loaded using a controlled replace-partition (Delete + Insert) strategy to ensure idempotency.

Internal file storage utilizes **Parquet**, which our benchmarks (`docs/format-comparison-and-partitioning.md`) proved to be 6.2x faster for reads and 82% smaller than the original CSVs, while guaranteeing schema fidelity.

## 5. Validation and Data Quality
Data quality is enforced by a robust testing framework with 3 separate gates:
*   **Raw Gate:** Checks schema presence, nullability, datatypes, valid ranges, and referential integrity against lookups.
*   **Staging Gate:** Verifies event key uniqueness, validates business rules (e.g., `unknown` category preservation), and reconciles row counts against the raw layer.
*   **Curated Gate:** Ensures PK constraints, rate limits (0 to 1), and complete referential integrity across the star schema.
Failures raise exceptions to halt the Airflow DAG immediately, preventing downstream corruption.

## 6. Orchestration and Deployment
The entire pipeline is orchestrated by Apache Airflow 2.10. The DAG is configured to run `@daily` with `catchup=True`, sequentially processing data partitions from 2022-09-16 to 2022-09-22. Retries are configured for transient errors, but data quality failures correctly halt execution.

The infrastructure is 100% containerized using Docker Compose, spinning up PostgreSQL, Airflow, and the Python execution environment deterministically. Configuration and secrets are cleanly externalized via `.env`.

## 7. Challenges and Limitations
*   **Data Fan-Out:** The raw data duplicated events for every video tag. We successfully collapsed this into a single event fact and a `video_categories` bridge table.
*   **Fuzzy Timestamps:** The source's `p_hour` field diverges from the UTC+8 hour for ~18% of rows. We used it as-is, meaning the 2-4 AM late-night boundary is fuzzy by up to an hour.
*   **Session Sparsity:** Because this is a sampled dataset, long unbroken sessions are rare, making absolute thresholding difficult. We recommend relative thresholds (e.g., 90th percentile) for downstream risk scoring.

## 8. Future Improvements
1. Implement the downstream risk-scoring logic that populates the `risk_scores` target table.
2. Replace the deterministic "first-occurrence" rule for the 6 ambiguous category labels with a manually reviewed mapping.
3. Transition to real-time streaming ingestion (e.g., Kafka) to enable immediate well-being nudges instead of batch-processed alerts.
