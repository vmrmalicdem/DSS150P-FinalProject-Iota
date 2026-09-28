-- Representative queries against the curated warehouse.

-- Q1. Users with the highest late-night share on a given day (minimum 5 events so shares are not noise).
SELECT user_id, feature_date, n_events, round(late_night_share::numeric, 3) AS late_night_share
FROM daily_user_features
WHERE feature_date = DATE '2022-09-18' AND n_events >= 5 AND late_night_share IS NOT NULL
ORDER BY late_night_share DESC, n_events DESC
LIMIT 10;

-- Q2. User-days combining a top-decile session length with at least one hate reaction.
-- The threshold is relative (90th percentile) because the sample logs only a few events per
-- user-day, so absolute cutoffs such as 30 minutes match nothing.
SELECT f.user_id, f.feature_date, f.max_session_seconds, f.hate_events, f.n_events
FROM daily_user_features f
WHERE f.hate_events >= 1
  AND f.max_session_seconds >= (SELECT percentile_cont(0.9) WITHIN GROUP (ORDER BY max_session_seconds)
                                FROM daily_user_features)
ORDER BY f.max_session_seconds DESC
LIMIT 10;

-- Q3. Average late-night share and rewatch rate by city tier and gender (users with enough history).
SELECT u.fre_city_level, u.gender,
       count(*)                              AS user_days,
       round(avg(f.late_night_share)::numeric, 4) AS avg_late_night_share,
       round(avg(f.rewatch_rate)::numeric, 4)     AS avg_rewatch_rate
FROM daily_user_features f
JOIN users u USING (user_id)
WHERE NOT u.is_sparse_history
GROUP BY u.fre_city_level, u.gender
ORDER BY user_days DESC;

-- Q4. Daily trend of the hate rate across all events (rare-event rate, aggregated rather than per session).
SELECT p_date, count(*) AS events, sum(hate::int) AS hate_events,
       round(100.0 * sum(hate::int) / count(*), 3) AS hate_pct
FROM interactions_curated
GROUP BY p_date
ORDER BY p_date;

-- Q5. Top level-1 content categories by total watch time (uses the video-category bridge and the lookup).
SELECT c.category_name_en, c.category_name_cn, count(DISTINCT i.user_id) AS users,
       round(sum(i.watch_time) / 3600.0, 1) AS watch_hours
FROM interactions_curated i
JOIN video_categories vc USING (pid)
JOIN categories c USING (category_id)
WHERE c.category_level = 1
GROUP BY c.category_name_en, c.category_name_cn
ORDER BY watch_hours DESC
LIMIT 10;

-- Q6. Trace one event from the warehouse back to its source batch (lineage).
SELECT user_id, pid, exposed_time, p_date, watch_time, is_rewatch_flagged, ingest_batch_id
FROM interactions_curated
WHERE user_id = 7313
ORDER BY exposed_time
LIMIT 5;
