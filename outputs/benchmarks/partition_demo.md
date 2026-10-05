### Partition sizes (`interactions_curated`, partition key `p_date`)

| p_date | Rows | Share of rows | Parquet size |
| --- | ---: | ---: | ---: |
| 20220916 | 22,533 | 17.4% | 598 KB |
| 20220917 | 23,439 | 18.1% | 625 KB |
| 20220918 | 22,130 | 17.1% | 598 KB |
| 20220919 | 17,268 | 13.3% | 472 KB |
| 20220920 | 17,739 | 13.7% | 479 KB |
| 20220921 | 13,869 | 10.7% | 389 KB |
| 20220922 | 12,505 | 9.7% | 357 KB |

Largest / smallest partition: 1.87x.

### Reading one day (`p_date=20220919`), curated Parquet

| Strategy | Time (s) | Speedup vs full scan | Files read | Rows read from disk | Rows returned | Bytes read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Partition read | 0.005 | 7.7x | 1 | 17,268 | 17,268 | 464 KB |
| Full scan + filter | 0.038 | 1.0x | 7 | 129,483 | 17,268 | 3.46 MB |
| Single file, default row groups | 0.016 | 2.3x | 1 | 129,483 | 17,268 | 3.15 MB |
| Single file, one row group per day | 0.005 | 7.1x | 1 | 17,268 | 17,268 | 464 KB |

### Reading one day (`p_date=20220919`), raw CSV layer

| Strategy | Time (s) | Speedup vs full scan | Files read | Rows read from disk | Rows returned | Bytes read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw CSV: one partition | 0.262 | 8.5x | 1 | 106,439 | 106,439 | 21.53 MB |
| Raw CSV: read all, filter | 2.223 | 1.0x | 7 | 794,053 | 106,439 | 160.72 MB |

Bytes read: compressed column data for Parquet, file size for CSV.
All strategies returned identical rows (checked before timing was reported).
