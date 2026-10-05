### `curated` dataset: 129,483 rows x 18 columns

| Format | Size (MB) | vs CSV | Write (s) | Read all (s) | Read 3 cols (s) | Read-all speedup vs CSV | 3-col speedup vs CSV | Columns exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CSV | 17.9 | 1.00x | 0.500 | 0.142 | 0.091 | 1.0x | 1.0x | 16/18 |
| CSV (gzip) | 3.4 | 0.19x | 1.844 | 0.195 | 0.137 | 0.7x | 0.7x | 16/18 |
| JSON (array) | 45.5 | 2.54x | 0.277 | 0.726 | 0.738 | 0.2x | 0.1x | 16/18 |
| JSON Lines | 45.5 | 2.54x | 0.507 | 0.837 | 0.833 | 0.2x | 0.1x | 16/18 |
| Parquet (snappy) | 3.2 | 0.18x | 0.060 | 0.023 | 0.003 | 6.2x | 27.0x | 18/18 |
| Parquet (zstd) | 2.7 | 0.15x | 0.065 | 0.021 | 0.004 | 6.6x | 25.9x | 18/18 |

Round-trip differences (read back with default settings):

- **CSV**: dtype changed: `p_date` (datetime64[ns] -> object); values changed: `watch_ratio` (max abs diff 7.11e-15)
- **CSV (gzip)**: dtype changed: `p_date` (datetime64[ns] -> object); values changed: `watch_ratio` (max abs diff 7.11e-15)
- **JSON (array)**: dtype changed: `p_date` (datetime64[ns] -> int64); values changed: `watch_ratio` (max abs diff 5.00e-11)
- **JSON Lines**: dtype changed: `p_date` (datetime64[ns] -> int64); values changed: `watch_ratio` (max abs diff 5.00e-11)
- **Parquet (snappy)**: all columns identical
- **Parquet (zstd)**: all columns identical

### `staged` dataset: 129,483 rows x 28 columns

| Format | Size (MB) | vs CSV | Write (s) | Read all (s) | Read 3 cols (s) | Read-all speedup vs CSV | 3-col speedup vs CSV | Columns exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CSV | 33.7 | 1.00x | 0.881 | 0.359 | 0.212 | 1.0x | 1.0x | 26/28 |
| CSV (gzip) | 8.3 | 0.25x | 2.497 | 0.465 | 0.328 | 0.8x | 0.6x | 26/28 |
| JSON (array) | 78.1 | 2.32x | 0.592 | 1.605 | 1.579 | 0.2x | 0.1x | 25/28 |
| JSON Lines | 78.1 | 2.32x | 1.155 | 1.894 | 1.877 | 0.2x | 0.1x | 25/28 |
| Parquet (snappy) | 6.1 | 0.18x | 0.161 | 0.070 | 0.004 | 5.1x | 56.1x | 28/28 |
| Parquet (zstd) | 5.0 | 0.15x | 0.166 | 0.071 | 0.004 | 5.1x | 54.0x | 28/28 |

Round-trip differences (read back with default settings):

- **CSV**: dtype changed: `p_date` (datetime64[ns] -> object); values changed: `watch_ratio` (max abs diff 7.11e-15)
- **CSV (gzip)**: dtype changed: `p_date` (datetime64[ns] -> object); values changed: `watch_ratio` (max abs diff 7.11e-15)
- **JSON (array)**: dtype changed: `p_date` (datetime64[ns] -> int64); values changed: `duration` (max abs diff 1.14e-13), `watch_ratio` (max abs diff 5.00e-11)
- **JSON Lines**: dtype changed: `p_date` (datetime64[ns] -> int64); values changed: `duration` (max abs diff 1.14e-13), `watch_ratio` (max abs diff 5.00e-11)
- **Parquet (snappy)**: all columns identical
- **Parquet (zstd)**: all columns identical
