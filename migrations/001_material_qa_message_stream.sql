-- Minimal material-QA context support without a conversation table.
ALTER TABLE consultation_messages
    ADD COLUMN book_id BIGINT UNSIGNED NULL AFTER user_id,
    ADD COLUMN is_context_reset TINYINT(1) NOT NULL DEFAULT 0 AFTER `references`,
    ADD INDEX idx_consultation_history (user_id, book_id, is_context_reset, id),
    ADD CONSTRAINT fk_consultation_messages_book
        FOREIGN KEY (book_id) REFERENCES books(id);
