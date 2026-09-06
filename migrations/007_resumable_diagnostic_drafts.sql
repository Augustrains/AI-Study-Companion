-- Keep unfinished diagnostic work separate from final diagnostic evidence.
-- The application also applies this compatibility change at startup because
-- legacy installations may not have a migration runner.
ALTER TABLE diagnostic_session
    ADD COLUMN draft_payload LONGTEXT NULL,
    ADD COLUMN completed_at DATETIME NULL,
    ADD COLUMN learning_plan_item_id BIGINT NULL;
