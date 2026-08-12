-- Least-privilege grants for localization review, publication, and feedback.
-- Apply after 006_localization_and_explanations.sql.

BEGIN;

GRANT SELECT ON student_quiz_localized_bank_safe TO app_student_api, app_scoring_service;
GRANT EXECUTE ON FUNCTION get_student_quiz_feedback(TEXT, TEXT) TO app_student_api;

GRANT SELECT, INSERT, UPDATE ON item_option_localizations,
    localization_review_records TO app_content_reviewer;
GRANT SELECT ON localization_publication_batches,
    localization_publication_batch_items TO app_content_reviewer;

GRANT SELECT ON learning_item_localizations, item_option_localizations,
    localization_review_records, localization_publication_batches,
    localization_publication_batch_items TO app_content_publisher;
GRANT EXECUTE ON FUNCTION publish_quiz_localization_batch(TEXT, TEXT, TEXT, TEXT, JSONB)
    TO app_content_publisher;

COMMIT;
