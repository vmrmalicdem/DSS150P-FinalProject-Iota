### `curated` dataset: 129,483 rows x 18 columns

| Format | Size (MB) | vs CSV | Write (s) | Read all (s) | Read 3 cols (s) | Read-all speedup vs CSV | 3-col speedup vs CSV | Columns exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CSV | 18.0 | 1.00x | 0.671 | 0.251 | 0.148 | 1.0x | 1.0x | 16/18 |
| CSV (gzip) | 3.4 | 0.19x | 1.812 | 0.284 | 0.187 | 0.9x | 0.8x | 16/18 |
| JSON (array) | 45.5 | 2.52x | 0.374 | 0.821 | 0.821 | 0.3x | 0.2x | 16/18 |
| JSON Lines | 45.5 | 2.52x | 0.570 | 1.034 | 0.945 | 0.2x | 0.2x | 16/18 |
| Parquet (snappy) | 3.1 | 0.17x | 0.076 | 0.011 | 0.003 | 22.4x | 43.6x | 18/18 |
| Parquet (zstd) | 2.6 | 0.14x | 0.085 | 0.011 | 0.003 | 23.6x | 43.4x | 18/18 |

Round-trip differences (read back with default settings):

- **CSV**: dtype changed: `p_date` (datetime64[us] -> str); values changed: `watch_ratio` (max abs diff 7.11e-15)
- **CSV (gzip)**: dtype changed: `p_date` (datetime64[us] -> str); values changed: `watch_ratio` (max abs diff 7.11e-15)
- **JSON (array)**: dtype changed: `p_date` (datetime64[us] -> int64); values changed: `watch_ratio` (max abs diff 5.00e-11)
- **JSON Lines**: dtype changed: `p_date` (datetime64[us] -> int64); values changed: `watch_ratio` (max abs diff 5.00e-11)
- **Parquet (snappy)**: all columns identical
- **Parquet (zstd)**: all columns identical

### `staged` dataset: 129,483 rows x 28 columns

| Format | Size (MB) | vs CSV | Write (s) | Read all (s) | Read 3 cols (s) | Read-all speedup vs CSV | 3-col speedup vs CSV | Columns exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CSV | 33.8 | 1.00x | 1.393 | 0.649 | 0.322 | 1.0x | 1.0x | 26/28 |
| CSV (gzip) | 8.3 | 0.24x | 2.989 | 0.723 | 0.407 | 0.9x | 0.8x | 26/28 |
| JSON (array) | 78.1 | 2.31x | 0.874 | 1.892 | 1.917 | 0.3x | 0.2x | 25/28 |
| JSON Lines | 78.1 | 2.31x | 1.387 | 2.076 | 2.060 | 0.3x | 0.2x | 25/28 |
| Parquet (snappy) | 6.0 | 0.18x | 0.154 | 0.022 | 0.004 | 29.6x | 84.4x | 28/28 |
| Parquet (zstd) | 5.0 | 0.15x | 0.170 | 0.026 | 0.004 | 24.7x | 82.0x | 28/28 |

Round-trip differences (read back with default settings):

- **CSV**: dtype changed: `p_date` (datetime64[us] -> str); values changed: `watch_ratio` (max abs diff 7.11e-15)
- **CSV (gzip)**: dtype changed: `p_date` (datetime64[us] -> str); values changed: `watch_ratio` (max abs diff 7.11e-15)
- **JSON (array)**: dtype changed: `p_date` (datetime64[us] -> int64); values changed: `duration` (max abs diff 1.14e-13), `watch_ratio` (max abs diff 5.00e-11)
- **JSON Lines**: dtype changed: `p_date` (datetime64[us] -> int64); values changed: `duration` (max abs diff 1.14e-13), `watch_ratio` (max abs diff 5.00e-11)
- **Parquet (snappy)**: all columns identical
- **Parquet (zstd)**: all columns identical
