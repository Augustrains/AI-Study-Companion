-- Public-read OSS stores the stable public URL directly in the attachment row.
ALTER TABLE consultation_message_attachments
    CHANGE COLUMN object_key file_url VARCHAR(512) NOT NULL,
    DROP INDEX uk_attachment_object_key,
    ADD UNIQUE INDEX uk_attachment_file_url (file_url);
