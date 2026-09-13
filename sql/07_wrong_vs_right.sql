-- 07. Чому не можна агрегувати до рівня користувача: три способи підрахунку одного й того ж CTR.
-- Спосіб A і B - типова помилка: користувач, який отримав 10 листів і клікнув один раз,
-- рахується як "клікнув", і CTR виходить завищений у 2.5 раза.
-- Спосіб C - правильний: одиниця спостереження = відправка.
-- Діалект: DuckDB / PostgreSQL / BigQuery.

-- A. Рівень користувача, знаменник = унікальні користувачі з рядком без реакції (так було в першій версії)
SELECT 'A: users w/o reaction as denominator' AS method,
       CASE WHEN ends_with(workflow, 'friday') THEN 'friday' ELSE 'tuesday' END AS send_day,
       COUNT(DISTINCT CASE WHEN action_type IS NULL THEN user_id END)   AS denominator,
       COUNT(DISTINCT CASE WHEN action_type = 'click' THEN user_id END) AS numerator,
       ROUND(COUNT(DISTINCT CASE WHEN action_type = 'click' THEN user_id END) * 100.0
           / COUNT(DISTINCT CASE WHEN action_type IS NULL THEN user_id END), 2) AS ctr_pct
FROM events
GROUP BY 1, 2

UNION ALL

-- B. Рівень користувача, знаменник = усі унікальні користувачі групи
SELECT 'B: all unique users as denominator',
       send_day,
       COUNT(DISTINCT user_id),
       COUNT(DISTINCT CASE WHEN clicked = 1 THEN user_id END),
       ROUND(COUNT(DISTINCT CASE WHEN clicked = 1 THEN user_id END) * 100.0 / COUNT(DISTINCT user_id), 2)
FROM observations
GROUP BY 1, 2

UNION ALL

-- C. Рівень відправки (правильно)
SELECT 'C: observations (user_id + sent_date)',
       send_day,
       COUNT(*),
       SUM(clicked),
       ROUND(AVG(clicked) * 100, 2)
FROM observations
GROUP BY 1, 2

ORDER BY 1, 2;
