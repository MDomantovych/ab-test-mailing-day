-- 01. Таблиця спостережень: одне повідомлення = (user_id, sent_date, workflow, notice_type).
-- Сирі дані — це LEFT JOIN відправок до дій:
--   * action_type IS NULL  -> відправка, на яку не було реакції (один рядок);
--   * opened / click       -> дії за тією ж відправкою (по рядку на кожну дію, окремого рядка відправки нема).
-- Тому агрегуємо до ключа відправки, а не до користувача.
-- Діалект: DuckDB / PostgreSQL (у BigQuery синтаксис ідентичний).

CREATE OR REPLACE VIEW observations AS
SELECT
    user_id,
    sent_date,
    workflow,
    notice_type,
    CASE WHEN ends_with(workflow, 'friday') THEN 'friday' ELSE 'tuesday' END AS send_day,
    REPLACE(REPLACE(workflow, '_friday', ''), '_tuesday', '')                AS wf_type,
    MAX(CASE WHEN action_type = 'opened' THEN 1 ELSE 0 END)                  AS opened,
    MAX(CASE WHEN action_type = 'click'  THEN 1 ELSE 0 END)                  AS clicked,
    SUM(CASE WHEN action_type = 'opened' THEN 1 ELSE 0 END)                  AS n_open,
    SUM(CASE WHEN action_type = 'click'  THEN 1 ELSE 0 END)                  AS n_click,
    MIN(CASE WHEN action_type = 'opened' THEN action_date END)               AS first_open,
    MIN(CASE WHEN action_type = 'click'  THEN action_date END)               AS first_click
FROM events
GROUP BY user_id, sent_date, workflow, notice_type;

-- Контроль: 35 527 спостережень, 4 578 користувачів, 2 285 з кліком
SELECT COUNT(*) AS observations, COUNT(DISTINCT user_id) AS users,
       SUM(opened) AS opened, SUM(clicked) AS clicked,
       ROUND(AVG(clicked) * 100, 2) AS ctr_pct
FROM observations;
