-- 04. Динаміка по тижнях: CTR friday vs tuesday у кожному календарному тижні (пн-нд).
-- Кожен тиждень — пара спостережень для парного порівняння; видно, чи ефект стабільний у часі.
-- Діалект: DuckDB / PostgreSQL. У BigQuery: DATE_TRUNC(DATE(sent_date), WEEK(MONDAY)).

SELECT
    CAST(DATE_TRUNC('week', sent_date) AS DATE)                       AS week_start,
    SUM(CASE WHEN send_day = 'friday'  THEN 1 ELSE 0 END)             AS sent_friday,
    SUM(CASE WHEN send_day = 'tuesday' THEN 1 ELSE 0 END)             AS sent_tuesday,
    ROUND(AVG(CASE WHEN send_day = 'friday'  THEN clicked END) * 100, 2) AS ctr_friday_pct,
    ROUND(AVG(CASE WHEN send_day = 'tuesday' THEN clicked END) * 100, 2) AS ctr_tuesday_pct,
    ROUND((AVG(CASE WHEN send_day = 'friday'  THEN clicked END)
         - AVG(CASE WHEN send_day = 'tuesday' THEN clicked END)) * 100, 2) AS diff_pp
FROM observations
GROUP BY 1
ORDER BY 1;
