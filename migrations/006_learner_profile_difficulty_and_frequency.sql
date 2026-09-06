-- Persist the remaining learner-profile preference controls.
-- MySQL 8.0 supports IF NOT EXISTS, so this migration is safe to re-run.
ALTER TABLE learner_profile
    ADD COLUMN IF NOT EXISTS preferred_difficulty VARCHAR(32) NULL AFTER preferred_content_style,
    ADD COLUMN IF NOT EXISTS learning_frequency VARCHAR(32) NULL AFTER preferred_difficulty;

-- Existing profiles were rendered with these defaults before the fields existed.
UPDATE learner_profile
SET preferred_difficulty = COALESCE(preferred_difficulty, 'adaptive'),
    learning_frequency = COALESCE(learning_frequency, 'flexible');
