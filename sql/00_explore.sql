-- 00. Первинне дослідження сирої таблиці events (41 925 рядків).
-- Діалект: DuckDB / PostgreSQL. У BigQuery: EXTRACT(DAYOFWEEK ...) замість DAYNAME, DATETIME замість TIMESTAMP.

-- 0.1 Які типи рядків є і чи action_date порожній рівно тоді, коли порожній action_type
SELECT
    COALESCE(action_type, 'NULL (без реакції)') AS row_kind,
    COUNT(*)                                     AS rows_cnt,
    SUM(CASE WHEN action_date IS NULL THEN 1 ELSE 0 END) AS action_date_null
FROM events
GROUP BY 1
ORDER BY 2 DESC;

-- 0.2 Скільки унікальних відправок ховається за рядками
SELECT
    COUNT(*)                                              AS rows_cnt,
    COUNT(DISTINCT user_id)                               AS users,
    COUNT(DISTINCT (user_id, sent_date))                  AS unique_user_sent,          -- 35 523
    COUNT(DISTINCT (user_id, sent_date, notice_type))     AS unique_user_sent_channel,  -- 35 527
    SUM(CASE WHEN action_type IS NULL THEN 1 ELSE 0 END)  AS rows_without_action        -- 30 461
FROM events;

-- 0.3 Чи є у рядків з дією "парний" рядок відправки (action_type IS NULL) з тим самим user_id + sent_date?
-- Відповідь: 0 — отже рядок з NULL є відправкою БЕЗ реакції, а не окремим логом відправок.
SELECT COUNT(*) AS action_rows_with_matching_null_row
FROM events a
JOIN events s
  ON s.user_id = a.user_id AND s.sent_date = a.sent_date AND s.action_type IS NULL
WHERE a.action_type IS NOT NULL;

-- 0.4 Розклад: день тижня відправки відповідає суфіксу workflow, але ГОДИНА різна (14:00 vs 16:00)
SELECT
    CASE WHEN ends_with(workflow, 'friday') THEN 'friday' ELSE 'tuesday' END AS send_day,
    dayname(sent_date)             AS weekday,
    EXTRACT(HOUR FROM sent_date)   AS send_hour,
    COUNT(DISTINCT (user_id, sent_date, notice_type)) AS messages
FROM events
GROUP BY 1, 2, 3
ORDER BY 1, 3;
