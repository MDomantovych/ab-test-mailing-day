-- 05. Втома від розсилок: CTR залежно від порядкового номера повідомлення для користувача.
-- Діалект: DuckDB / PostgreSQL / BigQuery.

WITH numbered AS (
    SELECT o.*,
           ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY sent_date, notice_type) AS msg_no
    FROM observations o
)
SELECT
    CASE WHEN msg_no = 1  THEN '1'
         WHEN msg_no = 2  THEN '2'
         WHEN msg_no = 3  THEN '3'
         WHEN msg_no <= 5 THEN '4-5'
         WHEN msg_no <= 10 THEN '6-10'
         WHEN msg_no <= 20 THEN '11-20'
         ELSE '21+' END                                            AS msg_bucket,
    MIN(msg_no)                                                    AS bucket_order,
    COUNT(*)                                                       AS sent,
    COUNT(DISTINCT user_id)                                        AS users,
    ROUND(AVG(clicked) * 100, 2)                                   AS ctr_pct,
    ROUND(AVG(CASE WHEN send_day = 'friday'  THEN clicked END) * 100, 2) AS ctr_friday_pct,
    ROUND(AVG(CASE WHEN send_day = 'tuesday' THEN clicked END) * 100, 2) AS ctr_tuesday_pct
FROM numbered
GROUP BY 1
ORDER BY bucket_order;
