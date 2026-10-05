# Data Engineering Architecture

The pipeline follows a modern data stack architecture deployed locally via Docker Compose.

```mermaid
graph TD
    subgraph Data Sources
        CSV[interaction_sampled.csv]
        Cats[categories_cn_en.csv]
        TXT[asr_en/*.txt]
        API[REST API Metadata]
    end

    subgraph Data Pipeline (Airflow Orchestrated)
        Ingest[Raw Ingestion]
        Stage[Staging & Transformation]
        Curate[Curation & Feature Eng.]
    end

    subgraph Storage Layer (Local Disk)
        Raw[Raw Layer: CSV/JSON/TXT]
        Staged[Staging Layer: Parquet]
        Curated[Curated Layer: Parquet]
    end

    subgraph Serving Layer
        Postgres[(PostgreSQL\nAnalytical DB)]
    end

    subgraph Consumption
        Notebooks[Jupyter Notebooks\nAnalytics & Demos]
    end

    %% Flow
    CSV --> Ingest
    Cats --> Ingest
    TXT --> Ingest
    API --> Ingest

    Ingest --> Raw
    Raw --> Stage
    Stage --> Staged
    Staged --> Curate
    Curate --> Curated

    Curated --> Postgres
    Postgres --> Notebooks
    
    %% Metadata
    classDef source fill:#f9f,stroke:#333,stroke-width:2px;
    classDef pipeline fill:#bbf,stroke:#333,stroke-width:2px;
    classDef storage fill:#bfb,stroke:#333,stroke-width:2px;
    
    class CSV,Cats,TXT,API source;
    class Ingest,Stage,Curate pipeline;
    class Raw,Staged,Curated storage;
```

## Component Roles
1. **Airflow (Orchestration):** Manages the daily incremental processing dependencies, ensuring tasks are run in the correct order (`Ingest -> Stage -> Curate -> Validate -> Load`).
2. **Local Storage (Data Lake):** Uses a directory structure to mimic object storage (S3/GCS). We utilize CSV for immutable raw landing and Parquet for optimized columnar staging and curated storage.
3. **PostgreSQL (Data Warehouse):** Serves as the relational structured storage where curated dimension and fact tables are exposed for SQL consumption.
4. **Jupyter (Analytics):** The downstream consumption environment for deriving behavioral insights.
