-- Multimodal requests consume the attachment and question together, so no
-- intermediate analysis text is persisted.
ALTER TABLE consultation_message_attachments
    DROP COLUMN analysis_text;
