# Short-Video Usage Pattern Analysis

Behavioral signals computed from the curated `daily_user_features` layer. These are descriptive screens, not validated measures of addiction or sleep loss.

## 0. Data coverage
- Curated partitions analysed: **7** (20220916 to 20220922)
- Raw partitions ingested: **7**
- Minimum events per user-day filter: **1** (no filter)

## 1. Exploratory statistics
- User-day records analysed: **5,533** (1,442 distinct users)
- Daily watch time: mean **192.6 s**, median **112.0 s**, 90th percentile **486.0 s**
- Longest single session: **1003.0 s**
- User-days with no watch time (late-night share undefined): **196**
- User-days with >50% of watch time in the late-night window (02:00-04:59): **142** (2.6%), from **110** distinct users

### Records per day
| p_date | user-days | users | avg watch (s) | late-night heavy user-days |
| --- | --- | --- | --- | --- |
| 20220916 | 831 | 831 | 217.5 | 19 |
| 20220917 | 838 | 838 | 219.7 | 23 |
| 20220918 | 865 | 865 | 209.3 | 25 |
| 20220919 | 761 | 761 | 186.0 | 22 |
| 20220920 | 791 | 791 | 197.5 | 12 |
| 20220921 | 744 | 744 | 162.9 | 16 |
| 20220922 | 703 | 703 | 143.4 | 25 |

## 2. Late-night usage
A subset of user-days spends most watch time inside the late-night window (02:00-04:59). This marks a late-night viewing pattern; the data has no sleep or well-being measure, so it cannot show sleep deprivation.

## 3. Rule-based screening flag (heuristic, not a risk score)
Three rules, each worth one point per user-day:
- Watch time above the 75th percentile (272.0 s)
- Hate rate above 1%
- Late-night share above 10%

| Flag level | user-days | share of user-days |
| --- | --- | --- |
| At least 1 rule | 1,547 | 28.0% |
| At least 2 rules | 98 | 1.8% |
| All 3 rules | 0 | 0.0% |

Individual rules: high watch time 1,383, hate rate 13, late-night 249.

The strictest level (all 3 rules) is the most defensible for review. A single rule is common and not meaningful alone. No outcome data exists to validate any level, so `risk_scores` remains unpopulated.

## 4. Visualizations
Not generated here. The columns above can be plotted in a notebook or a BI tool.
