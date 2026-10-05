# Data Flow and Lineage Diagram

This diagram traces the movement and transformation of data across the pipeline stages.

```mermaid
graph LR
    subgraph 1. Sources
        S1[interaction_sampled.csv]
        S2[categories_cn_en.csv]
        S3[asr_en / transcripts]
        S4[REST API]
    end

    subgraph 2. Raw Layer (Partitioned)
        R1[raw/interactions/p_date=*/interactions.csv]
        R2[raw/categories/categories_cn_en.csv]
        R3[raw/transcripts/asr_en/*.txt]
        R4[raw/risk_rules/rules.json]
    end

    subgraph 3. Staging Layer (Parquet)
        ST1[staging/events/p_date=*]
        ST2[staging/categories.parquet]
        ST3[staging/video_categories/p_date=*]
    end

    subgraph 4. Curated Layer (Parquet)
        C1[curated/interactions_curated/p_date=*]
        C2[curated/daily_user_features/p_date=*]
        C3[curated/dims/users.parquet]
        C4[curated/dims/videos.parquet]
    end

    subgraph 5. Postgres DB (Serving)
        DB1[(Fact: interactions_curated)]
        DB2[(Fact: daily_user_features)]
        DB3[(Dim: users, videos, categories)]
    end

    %% Movement
    S1 --> R1
    S2 --> R2
    S3 --> R3
    S4 --> R4

    %% Transformation
    R1 -->|Deduplicate & Parse| ST1
    R1 -->|Tag Flattening| ST3
    R2 -->|Type Casting| ST2
    
    ST1 -->|Join & Sessionize| C1
    ST1 -->|Aggregate Behaviors| C2
    ST1 -->|Extract Users| C3
    ST1 -->|Extract Videos| C4

    %% Loading
    C1 --> DB1
    C2 --> DB2
    C3 --> DB3
    C4 --> DB3
    ST2 --> DB3
    ST3 --> DB3

    classDef source fill:#f9f,stroke:#333;
    classDef raw fill:#eee,stroke:#333;
    classDef staging fill:#bbf,stroke:#333;
    classDef curated fill:#bfb,stroke:#333;
    classDef db fill:#ffb,stroke:#333;

    class S1,S2,S3,S4 source;
    class R1,R2,R3,R4 raw;
    class ST1,ST2,ST3 staging;
    class C1,C2,C3,C4 curated;
    class DB1,DB2,DB3 db;
```

## Key Transformations
- **Data Fan-Out resolution:** `raw/interactions.csv` contains comma-separated category IDs per row. Staging explodes this into a 1-to-many relationship tracked in `staging/video_categories`.
- **Deduplication:** Exact row duplicates (13% of source data) are dropped between Raw and Staging.
- **Cross-Partition Resolution:** Staging assigns an event exclusively to the earliest partition in which it was observed.
- **Behavioral Aggregation:** Curated features (`daily_user_features`) aggregate session lengths, watch ratios, and emotional signals (hate_rate) per user per day.
