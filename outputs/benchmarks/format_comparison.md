### `curated` dataset: 62,243 rows x 18 columns

| Format | Size (MB) | vs CSV | Write (s) | Read all (s) | Read 3 cols (s) | Read-all speedup vs CSV | 3-col speedup vs CSV | Columns exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CSV | 7.5 | 1.00x | 0.433 | 0.195 | 0.156 | 1.0x | 1.0x | 15/18 |
| CSV (gzip) | 1.7 | 0.22x | 0.777 | 0.219 | 0.158 | 0.9x | 1.0x | 15/18 |
| JSON (array) | 20.8 | 2.78x | 0.285 | 0.802 | 0.728 | 0.2x | 0.2x | 15/18 |
| JSON Lines | 20.8 | 2.78x | 0.346 | 0.666 | 0.740 | 0.3x | 0.2x | 15/18 |
| Parquet (snappy) | 1.7 | 0.22x | 0.055 | 0.008 | 0.003 | 23.6x | 48.0x | 18/18 |
| Parquet (zstd) | 1.4 | 0.19x | 0.056 | 0.009 | 0.003 | 21.9x | 46.7x | 18/18 |

Round-trip differences (read back with default settings):

- **CSV**: dtype changed: `p_date` (datetime64[us] -> str), `ingest_batch_id` (object -> float64); values changed: `watch_ratio` (max abs diff 3.55e-15)
- **CSV (gzip)**: dtype changed: `p_date` (datetime64[us] -> str), `ingest_batch_id` (object -> float64); values changed: `watch_ratio` (max abs diff 3.55e-15)
- **JSON (array)**: dtype changed: `p_date` (datetime64[us] -> int64), `ingest_batch_id` (object -> float64); values changed: `watch_ratio` (max abs diff 5.00e-11)
- **JSON Lines**: dtype changed: `p_date` (datetime64[us] -> int64), `ingest_batch_id` (object -> float64); values changed: `watch_ratio` (max abs diff 5.00e-11)
- **Parquet (snappy)**: all columns identical
- **Parquet (zstd)**: all columns identical

### `staged` dataset: 62,243 rows x 28 columns

| Format | Size (MB) | vs CSV | Write (s) | Read all (s) | Read 3 cols (s) | Read-all speedup vs CSV | 3-col speedup vs CSV | Columns exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CSV | 15.1 | 1.00x | 0.805 | 0.498 | 0.333 | 1.0x | 1.0x | 25/28 |
| CSV (gzip) | 3.9 | 0.26x | 1.613 | 0.626 | 0.418 | 0.8x | 0.8x | 25/28 |
| JSON (array) | 36.5 | 2.43x | 0.572 | 1.460 | 1.317 | 0.3x | 0.3x | 24/28 |
| JSON Lines | 36.5 | 2.43x | 0.957 | 1.735 | 1.481 | 0.3x | 0.2x | 24/28 |
| Parquet (snappy) | 3.5 | 0.23x | 0.226 | 0.027 | 0.011 | 18.8x | 31.7x | 28/28 |
| Parquet (zstd) | 2.9 | 0.19x | 0.389 | 0.036 | 0.010 | 14.0x | 34.7x | 28/28 |

Round-trip differences (read back with default settings):

- **CSV**: dtype changed: `p_date` (datetime64[us] -> str), `ingest_batch_id` (object -> float64); values changed: `watch_ratio` (max abs diff 3.55e-15)
- **CSV (gzip)**: dtype changed: `p_date` (datetime64[us] -> str), `ingest_batch_id` (object -> float64); values changed: `watch_ratio` (max abs diff 3.55e-15)
- **JSON (array)**: dtype changed: `p_date` (datetime64[us] -> int64), `ingest_batch_id` (object -> float64); values changed: `duration` (max abs diff 3.55e-15), `watch_ratio` (max abs diff 5.00e-11)
- **JSON Lines**: dtype changed: `p_date` (datetime64[us] -> int64), `ingest_batch_id` (object -> float64); values changed: `duration` (max abs diff 3.55e-15), `watch_ratio` (max abs diff 5.00e-11)
- **Parquet (snappy)**: all columns identical
- **Parquet (zstd)**: all columns identical
