-- 06. Перевірки якості даних, які впливають на інтерпретацію тесту.
-- Діалект: DuckDB / PostgreSQL. У BigQuery: TIMESTAMP_DIFF(action_date, sent_date, HOUR) замість date_diff.

-- 6.1 Зведення аномалій одним запитом
SELECT 'email: клік без відкриття (блокування картинок / трекінг-пікселя)' AS check_name,
       COUNT(*) AS cnt
FROM observations WHERE notice_type = 'email' AND clicked = 1 AND opened = 0
UNION ALL
SELECT 'push: є хоч одне opened (очікуємо 0 - відкриття push не трекаються)', COUNT(*)
FROM observations WHERE notice_type = 'push' AND opened = 1
UNION ALL
SELECT 'пара (user_id, sent_date) з двома каналами в одну секунду', COUNT(*)
FROM (SELECT user_id, sent_date FROM observations GROUP BY 1, 2 HAVING COUNT(*) > 1)
UNION ALL
SELECT 'дії раніше за відправку (action_date < sent_date)', COUNT(*)
FROM events WHERE action_date < sent_date
UNION ALL
SELECT 'користувачі-аномалії: >= 30 кліків за період (бот / автозавантаження)', COUNT(*)
FROM (SELECT user_id FROM observations GROUP BY 1 HAVING SUM(n_click) >= 30)
UNION ALL
SELECT 'відправки з >= 20 кліками за одним повідомленням', COUNT(*)
FROM observations WHERE n_click >= 20;

-- 6.2 Топ аномальних відправок (кандидати на виключення при перевірці стійкості)
SELECT user_id, sent_date, workflow, notice_type, n_open, n_click
FROM observations
ORDER BY n_click DESC
LIMIT 10;

-- 6.3 Час до першого кліку: скільки кліків приходить за 24 / 72 години
SELECT
    COUNT(*)                                                                         AS clicked_obs,
    ROUND(AVG(CASE WHEN date_diff('minute', sent_date, first_click) / 60.0 <= 24 THEN 1.0 ELSE 0 END) * 100, 1) AS within_24h_pct,
    ROUND(AVG(CASE WHEN date_diff('minute', sent_date, first_click) / 60.0 <= 72 THEN 1.0 ELSE 0 END) * 100, 1) AS within_72h_pct,
    ROUND(quantile_cont(date_diff('minute', sent_date, first_click) / 60.0, 0.5), 1)     AS median_hours
FROM observations
WHERE clicked = 1;
