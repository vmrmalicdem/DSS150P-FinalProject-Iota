| Stage | What | Rows / items |
| --- | --- | ---: |
| Source | interaction rows read | 794,053 |
| Source | category rows / transcript files | 826 / 10 |
| Raw | interaction rows kept (partitioned by date) | 794,053 |
| Staging | exact duplicate rows dropped (13.2%) | 104,519 |
| Staging | rows after de-duplication | 689,534 |
| Staging | events after tag fan-out collapse | 129,486 |
| Staging | events owned by an earlier partition (removed) | 3 |
| Staging | staged events | 129,483 |
| Curated | interactions_curated / daily_user_features | 129,483 / 25,109 |
| Curated | users / videos / categories / video_categories | 6,654 / 31,496 / 820 / 67,311 |
| Validation | raw gate: checks per partition (warnings / errors across run) | 19 (7 / 0) |
| Validation | staged gate: checks per partition (warnings / errors across run) | 10 (0 / 0) |
| Validation | curated gate: checks per partition (warnings / errors across run) | 11 (0 / 0) |
| PostgreSQL | categories, users, videos, video_categories, interactions_curated, daily_user_features, risk_scores | 820 / 6,654 / 31,496 / 67,311 / 129,483 / 25,109 / 0 |

Consistency checks: all hold.
