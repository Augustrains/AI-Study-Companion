-- Achievement catalogue and per-user unlock records.
-- Progress remains derived from learning source data; only definitions and unlocks are persisted.

CREATE TABLE IF NOT EXISTS achievement_definitions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(64) NOT NULL,
    description VARCHAR(255) NOT NULL,
    icon VARCHAR(16) NOT NULL,
    tone VARCHAR(24) NOT NULL DEFAULT 'blue',
    condition_type VARCHAR(40) NOT NULL,
    target_value BIGINT UNSIGNED NOT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_achievement_code (code),
    KEY idx_achievement_active_sort (is_active, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='荣誉勋章定义表';

CREATE TABLE IF NOT EXISTS user_achievements (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id BIGINT UNSIGNED NOT NULL,
    achievement_id BIGINT UNSIGNED NOT NULL,
    achieved_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notified_at DATETIME NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uk_user_achievement (user_id, achievement_id),
    KEY idx_user_achievement_notice (user_id, notified_at),
    CONSTRAINT fk_user_achievement_user FOREIGN KEY (user_id) REFERENCES users(user_id),
    CONSTRAINT fk_user_achievement_definition FOREIGN KEY (achievement_id) REFERENCES achievement_definitions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='用户勋章获得记录表';

INSERT INTO achievement_definitions
    (code, name, description, icon, tone, condition_type, target_value, sort_order)
VALUES
    ('first_steps', '初露锋芒', '累计完成 10 道题', '⚡', 'gold', 'answer_count', 10, 10),
    ('hundred_answers', '百题达人', '累计完成 100 道题', '📚', 'blue', 'answer_count', 100, 20),
    ('winning_streak', '连战连捷', '连续答对 5 题', '🔥', 'coral', 'longest_correct_streak', 5, 30),
    ('task_finisher', '行动派', '累计完成 10 个学习任务', '✅', 'violet', 'completed_task_count', 10, 40),
    ('focused_scholar', '专注学者', '累计学习 10 小时', '⏳', 'green', 'study_seconds', 36000, 50),
    ('weekly_podium', '巅峰之路', '本周综合成长榜进入前 3 名', '🏆', 'locked', 'weekly_rank', 3, 60)
ON DUPLICATE KEY UPDATE
    name=VALUES(name), description=VALUES(description), icon=VALUES(icon), tone=VALUES(tone),
    condition_type=VALUES(condition_type), target_value=VALUES(target_value),
    sort_order=VALUES(sort_order), is_active=1;
