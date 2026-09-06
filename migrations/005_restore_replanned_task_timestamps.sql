-- 修复旧版自适应重排遗漏 started_at 的已完成任务。
-- 仅回填当前活动计划中开始时间为空的记录，且只从同用户、同目标、同日期、
-- 同标题的历史完成任务复制已有的真实开始时间。
UPDATE learning_plan_day_item target
JOIN learning_plan_day target_day ON target_day.id = target.learning_plan_day_id
JOIN learning_plan target_plan ON target_plan.id = target_day.plan_id
JOIN (
    SELECT previous_plan.user_id,
           previous_plan.book_id,
           previous_plan.goal_id,
           previous_day.expected_date,
           previous_item.title,
           MAX(previous_item.started_at) AS started_at
    FROM learning_plan_day_item previous_item
    JOIN learning_plan_day previous_day ON previous_day.id = previous_item.learning_plan_day_id
    JOIN learning_plan previous_plan ON previous_plan.id = previous_day.plan_id
    WHERE previous_item.status = 'completed'
      AND previous_item.started_at IS NOT NULL
    GROUP BY previous_plan.user_id, previous_plan.book_id, previous_plan.goal_id,
             previous_day.expected_date, previous_item.title
) historical
  ON historical.user_id = target_plan.user_id
 AND historical.book_id = target_plan.book_id
 AND historical.goal_id = target_plan.goal_id
 AND historical.expected_date = target_day.expected_date
 AND historical.title = target.title
SET target.started_at = historical.started_at,
    target.updated_at = NOW()
WHERE target_plan.status = 'active'
  AND target.status = 'completed'
  AND target.started_at IS NULL;
