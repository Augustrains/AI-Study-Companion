-- Learner-profile fields collected by the profile form.
-- Apply once after 002_material_qa_socratic_mode.sql.
ALTER TABLE learner_profile
    ADD COLUMN self_assessed_level VARCHAR(32) NULL AFTER background,
    ADD COLUMN current_confusions TEXT NULL AFTER self_assessed_level,
    ADD COLUMN additional_requirements TEXT NULL AFTER current_confusions,
    ADD COLUMN preferred_activity_types JSON NULL AFTER preferred_content_style,
    ADD COLUMN session_duration_minutes SMALLINT UNSIGNED NULL AFTER preferred_activity_types;
