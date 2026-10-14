### Partition sizes (`interactions_curated`, partition key `p_date`)

| p_date | Rows | Share of rows | Parquet size |
| --- | ---: | ---: | ---: |
| 20220916 | 22,533 | 17.4% | 599 KB |
| 20220917 | 23,439 | 18.1% | 627 KB |
| 20220918 | 22,130 | 17.1% | 600 KB |
| 20220919 | 17,268 | 13.3% | 474 KB |
| 20220920 | 17,739 | 13.7% | 481 KB |
| 20220921 | 13,869 | 10.7% | 391 KB |
| 20220922 | 12,505 | 9.7% | 358 KB |

Largest / smallest partition: 1.87x.

### Reading one day (`p_date=20220919`), curated Parquet

| Strategy | Time (s) | Speedup vs full scan | Files read | Rows read from disk | Rows returned | Bytes read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Partition read | 0.004 | 8.7x | 1 | 17,268 | 17,268 | 464 KB |
| Full scan + filter | 0.037 | 1.0x | 7 | 129,483 | 17,268 | 3.46 MB |
| Single file, default row groups | 0.011 | 3.4x | 1 | 129,483 | 17,268 | 3.09 MB |
| Single file, one row group per day | 0.006 | 6.8x | 1 | 17,268 | 17,268 | 464 KB |

### Reading one day (`p_date=20220919`), raw CSV layer

| Strategy | Time (s) | Speedup vs full scan | Files read | Rows read from disk | Rows returned | Bytes read |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Raw CSV: one partition | 0.486 | 8.1x | 1 | 106,439 | 106,439 | 21.53 MB |
| Raw CSV: read all, filter | 3.947 | 1.0x | 7 | 794,053 | 106,439 | 160.72 MB |

Bytes read: compressed column data for Parquet, file size for CSV.
All strategies returned identical rows (checked before timing was reported).
