-- 03. Розрізи: канал (email / push) і тип воркфлоу (ThisWeek / ThisMonth) x день відправки.
-- Перевіряємо, чи ефект дня однаковий у всіх сегментах.
-- Діалект: DuckDB / PostgreSQL / BigQuery.

-- 3.1 Канал x день
SELECT notice_type,
       send_day,
       COUNT(*)                                   AS sent,
       COUNT(DISTINCT user_id)                    AS users,
       SUM(opened)                                AS opened,
       SUM(clicked)                               AS clicked,
       ROUND(AVG(opened)  * 100, 2)               AS open_rate_pct,   -- для push завжди 0: відкриття не трекаються
       ROUND(AVG(clicked) * 100, 2)               AS ctr_pct,
       ROUND(SUM(clicked) * 100.0 / NULLIF(SUM(opened), 0), 1) AS ctor_pct  -- клік серед тих, хто відкрив (лише email)
FROM observations
GROUP BY 1, 2
ORDER BY 1, 2;

-- 3.2 Тип воркфлоу x день
SELECT wf_type,
       send_day,
       COUNT(*)                     AS sent,
       SUM(clicked)                 AS clicked,
       ROUND(AVG(clicked) * 100, 2) AS ctr_pct
FROM observations
GROUP BY 1, 2
ORDER BY 1, 2;

-- 3.3 Канал x воркфлоу x день (найдрібніший розріз)
SELECT notice_type, wf_type, send_day,
       COUNT(*)                     AS sent,
       SUM(clicked)                 AS clicked,
       ROUND(AVG(clicked) * 100, 2) AS ctr_pct
FROM observations
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
