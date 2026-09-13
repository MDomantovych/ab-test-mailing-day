-- 02. Основний A/B-тест: friday vs tuesday на рівні спостережень (відправок).
-- Метрика: CTR = частка відправок, за якими був хоча б один клік.
-- Тут же рахуємо z-статистику двовибіркового тесту пропорцій (пул-оцінка p).
-- Діалект: DuckDB / PostgreSQL / BigQuery.

WITH g AS (
    SELECT send_day,
           COUNT(*)                 AS sent,
           SUM(clicked)             AS clicked,
           SUM(clicked) * 1.0 / COUNT(*) AS ctr
    FROM observations
    GROUP BY send_day
),
pooled AS (
    SELECT SUM(clicked) * 1.0 / SUM(sent) AS p_pool FROM g
)
SELECT
    f.sent                          AS sent_friday,
    f.clicked                       AS clicked_friday,
    ROUND(f.ctr * 100, 2)           AS ctr_friday_pct,
    t.sent                          AS sent_tuesday,
    t.clicked                       AS clicked_tuesday,
    ROUND(t.ctr * 100, 2)           AS ctr_tuesday_pct,
    ROUND((f.ctr - t.ctr) * 100, 2) AS diff_pp,
    ROUND((f.ctr / t.ctr - 1) * 100, 1) AS uplift_pct,
    -- 95% ДІ різниці (нормальна апроксимація, незалежні спостереження)
    ROUND((f.ctr - t.ctr - 1.96 * SQRT(f.ctr*(1-f.ctr)/f.sent + t.ctr*(1-t.ctr)/t.sent)) * 100, 2) AS diff_ci_low_pp,
    ROUND((f.ctr - t.ctr + 1.96 * SQRT(f.ctr*(1-f.ctr)/f.sent + t.ctr*(1-t.ctr)/t.sent)) * 100, 2) AS diff_ci_high_pp,
    ROUND((f.ctr - t.ctr) / SQRT(p.p_pool * (1 - p.p_pool) * (1.0/f.sent + 1.0/t.sent)), 2)      AS z_stat
FROM g f
CROSS JOIN g t
CROSS JOIN pooled p
WHERE f.send_day = 'friday' AND t.send_day = 'tuesday';
