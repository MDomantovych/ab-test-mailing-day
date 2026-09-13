-- 08. Перетин груп і перевірка, чи призначення дня залежить від відгуку користувача.
-- Діалект: DuckDB / PostgreSQL. У BigQuery: DATE_TRUNC(DATE(sent_date), WEEK(MONDAY)).

-- 8.1 Перетин за весь період: скільки користувачів бачили обидва дні
SELECT
    COUNT(*)                                          AS users,
    SUM(CASE WHEN days_seen = 2 THEN 1 ELSE 0 END)    AS users_both_days,
    ROUND(AVG(CASE WHEN days_seen = 2 THEN 1.0 ELSE 0 END) * 100, 1) AS both_days_pct
FROM (SELECT user_id, COUNT(DISTINCT send_day) AS days_seen FROM observations GROUP BY 1);

-- 8.2 Перетин усередині календарного тижня (пн-нд): user-week, у якому були і tuesday, і friday
SELECT
    COUNT(*)                                          AS user_weeks,
    SUM(CASE WHEN days_seen = 2 THEN 1 ELSE 0 END)    AS user_weeks_both_days,
    ROUND(AVG(CASE WHEN days_seen = 2 THEN 1.0 ELSE 0 END) * 100, 1) AS both_days_pct
FROM (
    SELECT user_id, DATE_TRUNC('week', sent_date) AS wk, COUNT(DISTINCT send_day) AS days_seen
    FROM observations GROUP BY 1, 2
);

-- 8.3 Селекція: чи частіше отримують friday-повідомлення ті, хто клікнув у tuesday того ж тижня?
-- Якщо частки однакові — призначення не залежить від реакції, і порівняння днів коректне.
WITH tue AS (
    SELECT user_id, DATE_TRUNC('week', sent_date) AS wk, MAX(clicked) AS tue_clicked
    FROM observations WHERE send_day = 'tuesday' GROUP BY 1, 2
),
fri AS (
    SELECT DISTINCT user_id, DATE_TRUNC('week', sent_date) AS wk
    FROM observations WHERE send_day = 'friday'
)
SELECT tue.tue_clicked,
       COUNT(*)                                             AS tuesday_user_weeks,
       ROUND(AVG(CASE WHEN fri.user_id IS NOT NULL THEN 1.0 ELSE 0 END) * 100, 1) AS got_friday_same_week_pct
FROM tue
LEFT JOIN fri USING (user_id, wk)
GROUP BY 1
ORDER BY 1;
