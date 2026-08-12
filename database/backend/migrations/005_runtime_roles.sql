-- Optional DBA migration: least-privilege runtime group roles.
-- Apply after 004_runtime_hardening.sql and all generated seeds.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_student_api') THEN
        CREATE ROLE app_student_api NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_scoring_service') THEN
        CREATE ROLE app_scoring_service NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_content_reviewer') THEN
        CREATE ROLE app_content_reviewer NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_content_publisher') THEN
        CREATE ROLE app_content_publisher NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO app_student_api, app_scoring_service,
    app_content_reviewer, app_content_publisher;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_student_api;
GRANT SELECT ON student_quiz_bank_safe, published_quiz_bank,
    student_practice_task_bank_safe, practice_task_bank TO app_student_api;
GRANT SELECT, INSERT, UPDATE ON assessment_assignments, task_submissions,
    api_idempotency_records, item_quality_statistics TO app_student_api;
GRANT SELECT ON evaluation_results TO app_student_api;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_scoring_service;
GRANT SELECT ON student_quiz_bank_safe, internal_quiz_scoring_bank,
    internal_practice_task_bank, evaluation_test_cases,
    evaluation_rubric_criteria TO app_scoring_service;
GRANT SELECT, INSERT, UPDATE ON assessment_assignments, task_submissions,
    evaluation_results, notebook_execution_runs, assessment_evidence,
    api_idempotency_records, item_quality_statistics TO app_scoring_service;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_content_reviewer;
GRANT SELECT ON source_repositories, source_documents, learning_items,
    learning_item_versions, item_options, knowledge_nodes, item_knowledge_maps,
    item_knowledge_map_candidates, knowledge_edge_candidates,
    learning_item_enrichment_candidates, learning_item_localizations,
    evaluation_specs, question_review_records,
    content_review_batches, content_review_batch_items, publication_batches,
    publication_batch_items, content_review_queue, publication_readiness
    TO app_content_reviewer;
GRANT INSERT, UPDATE ON item_knowledge_map_candidates, knowledge_edge_candidates,
    learning_item_enrichment_candidates, learning_item_localizations,
    question_review_records, content_review_batches, content_review_batch_items
    TO app_content_reviewer;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_content_publisher;
GRANT SELECT ON source_repositories, source_documents, learning_items,
    learning_item_versions, item_options, knowledge_nodes,
    item_knowledge_map_candidates, evaluation_specs, question_review_records,
    publication_batches, publication_batch_items, publication_readiness
    TO app_content_publisher;
GRANT EXECUTE ON FUNCTION publish_quiz_batch(TEXT, TEXT, TEXT, JSONB, TEXT, JSONB)
    TO app_content_publisher;

-- Student-facing row isolation. The API must set the authenticated user for
-- every transaction: SET LOCAL app.current_user_id = '<server-verified-id>'.
ALTER TABLE assessment_assignments ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_submissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluation_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_idempotency_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE assessment_evidence ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS assignments_student_scope ON assessment_assignments;
CREATE POLICY assignments_student_scope ON assessment_assignments
    FOR ALL TO app_student_api
    USING (user_id = current_setting('app.current_user_id', TRUE))
    WITH CHECK (user_id = current_setting('app.current_user_id', TRUE));
DROP POLICY IF EXISTS assignments_scoring_scope ON assessment_assignments;
CREATE POLICY assignments_scoring_scope ON assessment_assignments
    FOR ALL TO app_scoring_service USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS submissions_student_scope ON task_submissions;
CREATE POLICY submissions_student_scope ON task_submissions
    FOR ALL TO app_student_api
    USING (user_id = current_setting('app.current_user_id', TRUE))
    WITH CHECK (user_id = current_setting('app.current_user_id', TRUE));
DROP POLICY IF EXISTS submissions_scoring_scope ON task_submissions;
CREATE POLICY submissions_scoring_scope ON task_submissions
    FOR ALL TO app_scoring_service USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS results_student_scope ON evaluation_results;
CREATE POLICY results_student_scope ON evaluation_results
    FOR SELECT TO app_student_api
    USING (EXISTS (
        SELECT 1 FROM task_submissions AS submission
        WHERE submission.submission_id = evaluation_results.submission_id
          AND submission.user_id = current_setting('app.current_user_id', TRUE)
    ));
DROP POLICY IF EXISTS results_scoring_scope ON evaluation_results;
CREATE POLICY results_scoring_scope ON evaluation_results
    FOR ALL TO app_scoring_service USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS idempotency_student_scope ON api_idempotency_records;
CREATE POLICY idempotency_student_scope ON api_idempotency_records
    FOR ALL TO app_student_api
    USING (actor_id = current_setting('app.current_user_id', TRUE))
    WITH CHECK (actor_id = current_setting('app.current_user_id', TRUE));
DROP POLICY IF EXISTS idempotency_scoring_scope ON api_idempotency_records;
CREATE POLICY idempotency_scoring_scope ON api_idempotency_records
    FOR ALL TO app_scoring_service USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS evidence_scoring_scope ON assessment_evidence;
CREATE POLICY evidence_scoring_scope ON assessment_evidence
    FOR ALL TO app_scoring_service USING (TRUE) WITH CHECK (TRUE);

COMMIT;
