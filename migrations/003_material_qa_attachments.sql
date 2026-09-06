-- Metadata for images and short PDFs attached to material-QA messages.
-- File bytes live in OSS; only the stable OSS object key is stored here.
CREATE TABLE IF NOT EXISTS consultation_message_attachments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    message_id BIGINT UNSIGNED NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_type VARCHAR(64) NOT NULL,
    file_size BIGINT UNSIGNED NOT NULL,
    file_url VARCHAR(512) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uk_attachment_file_url (file_url),
    KEY idx_attachment_message_id (message_id),

    CONSTRAINT fk_attachment_message
        FOREIGN KEY (message_id)
        REFERENCES consultation_messages(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Material-QA message attachment metadata';
