-- Least-privilege algorithm role and mastery row isolation.
-- Apply after 008_algorithm_and_mastery.sql.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_learning_algorithm') THEN
        CREATE ROLE app_learning_algorithm NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO app_learning_algorithm;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_learning_algorithm;
GRANT SELECT ON algorithm_knowledge_catalog, algorithm_question_catalog,
    algorithm_prerequisite_graph, algorithm_evidence_feed,
    algorithm_learner_state TO app_learning_algorithm;
GRANT EXECUTE ON FUNCTION apply_mastery_update(TEXT, TEXT, INTEGER, TEXT, JSONB)
    TO app_learning_algorithm;

GRANT SELECT ON student_knowledge_status_safe, student_mastery_history_safe
    TO app_student_api;
GRANT SELECT ON knowledge_edges, knowledge_edge_candidates,
    knowledge_edge_review_records, knowledge_edge_publication_batches,
    knowledge_edge_publication_batch_items TO app_content_reviewer;
GRANT INSERT ON knowledge_edge_review_records TO app_content_reviewer;
GRANT SELECT ON knowledge_edge_candidates, knowledge_edge_publication_batches,
    knowledge_edge_publication_batch_items TO app_content_publisher;
GRANT EXECUTE ON FUNCTION publish_knowledge_edge_batch(TEXT, TEXT, TEXT, TEXT, JSONB)
    TO app_content_publisher;

ALTER TABLE learner_mastery_current ENABLE ROW LEVEL SECURITY;
ALTER TABLE learner_mastery_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE mastery_evidence_processing ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS mastery_current_student_scope ON learner_mastery_current;
CREATE POLICY mastery_current_student_scope ON learner_mastery_current
    FOR SELECT TO app_student_api
    USING (user_id = current_setting('app.current_user_id', TRUE));
DROP POLICY IF EXISTS mastery_current_algorithm_scope ON learner_mastery_current;
CREATE POLICY mastery_current_algorithm_scope ON learner_mastery_current
    FOR ALL TO app_learning_algorithm USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS mastery_history_student_scope ON learner_mastery_history;
CREATE POLICY mastery_history_student_scope ON learner_mastery_history
    FOR SELECT TO app_student_api
    USING (user_id = current_setting('app.current_user_id', TRUE));
DROP POLICY IF EXISTS mastery_history_algorithm_scope ON learner_mastery_history;
CREATE POLICY mastery_history_algorithm_scope ON learner_mastery_history
    FOR ALL TO app_learning_algorithm USING (TRUE) WITH CHECK (TRUE);

DROP POLICY IF EXISTS mastery_processing_algorithm_scope ON mastery_evidence_processing;
CREATE POLICY mastery_processing_algorithm_scope ON mastery_evidence_processing
    FOR ALL TO app_learning_algorithm USING (TRUE) WITH CHECK (TRUE);

COMMIT;
