-- 回填历史任务/计划日时间字段。
-- 已完成任务至少拥有可追溯的开始和完成时间；计划日时间由其任务聚合得到。
UPDATE learning_plan_day_item
SET started_at = completed_at,
    updated_at = NOW()
WHERE status = 'completed'
  AND started_at IS NULL
  AND completed_at IS NOT NULL;

UPDATE learning_plan_day d
JOIN (
    SELECT learning_plan_day_id AS day_id,
           MIN(COALESCE(started_at, completed_at)) AS first_started,
           MAX(completed_at) AS last_completed,
           SUM(status NOT IN ('completed', 'skipped', 'rescheduled')) AS pending
    FROM learning_plan_day_item
    GROUP BY learning_plan_day_id
) x ON x.day_id = d.id
SET d.started_at = COALESCE(d.started_at, x.first_started),
    d.completed_at = CASE
        WHEN x.pending = 0 THEN COALESCE(d.completed_at, x.last_completed)
        ELSE d.completed_at
    END,
    d.updated_at = NOW()
WHERE d.started_at IS NULL
   OR (x.pending = 0 AND d.completed_at IS NULL);
