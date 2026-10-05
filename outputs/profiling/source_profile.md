## interaction_sampled.csv: 794,053 rows x 28 columns, 159.9 MB

- p_date range 20220916 to 20220922 across 7 partitions; hours with no rows: [0, 1]
- schema matches the pipeline's expected columns: True
- exact duplicate rows: 104,519 (13.16%)
- unique events (user, video, exposure time): 129,483; rows per event: min 1, median 6, mean 6.13, max 675; distribution {'1': 6516, '2': 15096, '3': 30556, '4': 11289, '5+': 66026}
- events present in more than one p_date partition: 3
- exposed_time spans 2022-09-15T17:44:56 to 2022-09-22T15:52:09 (UTC)
- p_date equals the UTC date of exposed_time for 89.82% of rows, and the UTC+8 date for 100.00%
- p_hour equals the UTC hour for 0.00% of rows, and the UTC+8 hour for 81.88%
- rows with watch_time > duration: 219,522 (27.65%)
- titles with a line break inside a quoted field: 87
- category ids used / absent from the lookup: 631 / 0

| Column | Distinct | Missing | 'unknown' | Min | Median | Max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| user_id | 6,654 | 0 | 0 | 1 | 4,806 | 9,999 |
| pid | 31,496 | 0 | 0 | 1 | 38,355 | 153,523 |
| author_id | 23,242 | 0 | 0 | 3 | 1,966,647,634 | 3,015,380,385 |
| category_id | 631 | 0 | 0 | 1 | 136 | 2,357 |
| category_level | 3 | 0 | 0 | 1 | 2 | 3 |
| parent_id | 110 | 0 | 0 | 1 | 26 | 593 |
| root_id | 38 | 0 | 0 | 1 | 20 | 541 |
| exposed_time | 101,847 | 0 | 0 | 1,663,263,896 | 1,663,507,324 | 1,663,861,929 |
| author_fans_count | 75,448 | 0 | 0 | 1 | 153,378 | 215,859,160 |
| watch_time | 587 | 0 | 0 | 0 | 13 | 922 |
| duration | 14,519 | 0 | 0 | 3.958 | 83.72 | 1,735 |
| cvm_like | 2 | 0 | 0 |  |  |  |
| click | 2 | 0 | 0 |  |  |  |
| comment | 2 | 0 | 0 |  |  |  |
| follow | 2 | 0 | 0 |  |  |  |
| collect | 2 | 0 | 0 |  |  |  |
| forward | 2 | 0 | 0 |  |  |  |
| hate | 2 | 0 | 0 |  |  |  |
| tag_name | 26,355 | 0 | 0 |  |  |  |
| title | 30,154 | 0 | 0 |  |  |  |
| p_hour | 22 | 0 | 0 | 2 | 16 | 23 |
| p_date | 7 | 0 | 0 |  |  |  |
| gender | 2 | 0 | 0 |  |  |  |
| age | 60 | 0 | 0 | 20 | 40 | 79 |
| mod_price | 271 | 0 | 0 | 399 | 1,599 | 17,799 |
| fre_city | 365 | 0 | 0 |  |  |  |
| fre_community_type | 4 | 0 | 256,974 |  |  |  |
| fre_city_level | 7 | 0 | 520 |  |  |  |

## categories_cn_en.csv: 826 rows x 6 columns

- distinct category ids: 820; ids appearing more than once: [233, 239, 338, 350, 354, 368] (12 rows)
- blank English labels: 4; English labels with a leading space: 786
- level distribution: {'1': 36, '2': 307, '3': 483}

## asr_en transcripts: 10 files

- bytes 102 to 578; words 17 to 117; undecodable 0; empty 0
- matching a video id: 9 of 10; not matching: ['7']; coverage of 31,496 videos: 0.0286%

## Findings

| Finding | Count | Share |
| --- | ---: | ---: |
| exact duplicate rows | 104,519 | 13.16% |
| rows beyond one per event (tag fan-out and duplicates) | 664,570 | 83.69% |
| events present in more than one p_date partition | 3 | |
| rows with watch_time greater than duration | 219,522 | 27.65% |
| titles containing a line break inside a quoted field | 87 | |
| hours of the day with no rows | 2 | |
| fre_community_type holds the literal value 'unknown' | 256,974 | 32.36% |
| fre_city_level holds the literal value 'unknown' | 520 | 0.07% |
| category ids appearing more than once in the lookup | 6 | |
| blank English category labels | 4 | |
| English labels with a leading space | 786 | |
| transcript files whose name matches no video id | 1 | |
