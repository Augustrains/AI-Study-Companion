-- Stateful Socratic tutoring metadata. A learning_task_id identifies one
-- explicitly started problem-solving task; it is not a chat session.
ALTER TABLE consultation_messages
    ADD COLUMN qa_mode VARCHAR(16) NOT NULL DEFAULT 'direct' AFTER is_context_reset,
    ADD COLUMN learning_task_id VARCHAR(64) NULL AFTER qa_mode,
    ADD COLUMN socratic_state VARCHAR(16) NULL AFTER learning_task_id,
    ADD COLUMN response_quality VARCHAR(16) NULL AFTER socratic_state,
    ADD COLUMN socratic_completed TINYINT(1) NOT NULL DEFAULT 0 AFTER response_quality,
    ADD INDEX idx_consultation_learning_task
        (user_id, book_id, learning_task_id, id);
