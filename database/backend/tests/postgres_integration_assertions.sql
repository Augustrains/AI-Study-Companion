\set ON_ERROR_STOP on

DO $$
DECLARE
    quiz RECORD;
    source_snapshot JSONB;
    release_payload JSONB;
    localization_payload JSONB;
    released INTEGER;
    selected_key TEXT;
    result_id TEXT := 'integration-result';
    edge RECORD;
    edge_payload JSONB;
    mastery_payload JSONB;
BEGIN
    IF (SELECT count(*) FROM learning_items) <> 423 THEN
        RAISE EXCEPTION 'Expected 423 learning items';
    END IF;
    IF (SELECT count(*) FROM item_knowledge_map_candidates) <> 423 THEN
        RAISE EXCEPTION 'Expected 423 mapping candidates';
    END IF;
    IF (SELECT count(*) FROM item_knowledge_map_candidates AS candidate
        JOIN learning_item_versions AS version USING (learning_item_version_id)
        JOIN learning_items AS item USING (learning_item_id)
        WHERE item.item_type = 'quiz_question') <> 301 THEN
        RAISE EXCEPTION 'Expected 301 Quiz mapping candidates';
    END IF;
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN ('student_quiz_bank_safe', 'student_practice_task_bank_safe')
          AND column_name IN ('answer_data', 'is_correct', 'correct_option_key', 'evaluation_config')
    ) THEN
        RAISE EXCEPTION 'A student-safe view exposes an answer field';
    END IF;
    IF has_table_privilege('app_student_api', 'learning_item_versions', 'SELECT') THEN
        RAISE EXCEPTION 'Student role can read learning_item_versions';
    END IF;
    IF NOT has_table_privilege('app_student_api', 'student_quiz_bank_safe', 'SELECT') THEN
        RAISE EXCEPTION 'Student role cannot read the safe Quiz view';
    END IF;
    IF has_table_privilege('app_content_reviewer', 'learning_items', 'UPDATE') THEN
        RAISE EXCEPTION 'Reviewer role can bypass publication by updating learning_items';
    END IF;
    IF NOT has_function_privilege(
        'app_content_publisher',
        'publish_quiz_batch(text,text,text,jsonb,text,jsonb)',
        'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'Publisher role cannot call publish_quiz_batch';
    END IF;
    IF NOT has_function_privilege(
        'app_content_publisher',
        'publish_quiz_localization_batch(text,text,text,text,jsonb)',
        'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'Publisher role cannot call publish_quiz_localization_batch';
    END IF;
    IF has_table_privilege('app_content_publisher', 'learning_item_localizations', 'UPDATE')
       OR has_table_privilege('app_content_publisher', 'item_option_localizations', 'UPDATE') THEN
        RAISE EXCEPTION 'Publisher role can directly update localization content';
    END IF;
    IF has_table_privilege('app_learning_algorithm', 'learning_item_versions', 'SELECT')
       OR has_table_privilege('app_learning_algorithm', 'item_options', 'SELECT')
       OR has_table_privilege('app_learning_algorithm', 'learner_mastery_current', 'UPDATE') THEN
        RAISE EXCEPTION 'Algorithm role has direct answer or mastery table access';
    END IF;
    IF NOT has_table_privilege('app_learning_algorithm', 'algorithm_question_catalog', 'SELECT')
       OR NOT has_function_privilege(
            'app_learning_algorithm',
            'apply_mastery_update(text,text,integer,text,jsonb)', 'EXECUTE'
       ) THEN
        RAISE EXCEPTION 'Algorithm role is missing its safe contract';
    END IF;

    SELECT
        item.learning_item_id AS item_id,
        version.learning_item_version_id AS version_id,
        version.stem,
        version.answer_data ->> 'answer' AS answer_text,
        document.source_id,
        document.content_version AS source_commit,
        document.content_hash AS source_content_hash,
        candidate.mapping_candidate_id AS candidate_id,
        candidate.knowledge_point_id,
        candidate.confidence,
        (SELECT option.option_key FROM item_options AS option
         WHERE option.learning_item_version_id = version.learning_item_version_id
           AND option.is_correct = TRUE LIMIT 1) AS correct_option_key
    INTO quiz
    FROM learning_items AS item
    JOIN learning_item_versions AS version
      ON version.learning_item_version_id = item.current_version_id
    JOIN source_documents AS document
      ON document.source_document_id = item.source_document_id
    JOIN item_knowledge_map_candidates AS candidate
      ON candidate.learning_item_version_id = version.learning_item_version_id
     AND candidate.relation_type = 'target'
    WHERE item.item_type = 'quiz_question'
    ORDER BY item.learning_item_id
    LIMIT 1;

    SELECT jsonb_object_agg(source_id, commit_sha)
    INTO source_snapshot
    FROM source_repositories;

    release_payload := jsonb_build_array(jsonb_build_object(
        'itemId', quiz.item_id,
        'versionId', quiz.version_id,
        'sourceId', quiz.source_id,
        'sourceCommit', quiz.source_commit,
        'sourceContentHash', quiz.source_content_hash,
        'questionStem', quiz.stem,
        'answerText', quiz.answer_text,
        'correctOptionKey', quiz.correct_option_key,
        'knowledgePointId', quiz.knowledge_point_id,
        'candidateId', quiz.candidate_id,
        'mappingConfidence', quiz.confidence::text,
        'reviewerId', 'integration-reviewer',
        'reviewerNote', 'PostgreSQL integration test'
    ));

    released := publish_quiz_batch(
        'integration-publication', 'Integration publication', 'integration-publisher',
        source_snapshot, 'integration-manifest', release_payload
    );
    IF released <> 1 THEN
        RAISE EXCEPTION 'Expected one published Quiz';
    END IF;
    IF (SELECT count(*) FROM student_quiz_bank_safe) <> 1 THEN
        RAISE EXCEPTION 'Published Quiz is missing from the student-safe view';
    END IF;
    IF (SELECT count(*) FROM learning_item_localizations WHERE locale = 'zh-CN') <> 301 THEN
        RAISE EXCEPTION 'Expected 301 zh-CN localization candidates';
    END IF;
    IF (SELECT count(*) FROM item_option_localizations WHERE locale = 'zh-CN') <> 856 THEN
        RAISE EXCEPTION 'Expected 856 zh-CN option localization candidates';
    END IF;
    IF EXISTS (SELECT 1 FROM student_quiz_localized_bank_safe WHERE locale = 'zh-CN') THEN
        RAISE EXCEPTION 'Unreviewed zh-CN localization leaked into student view';
    END IF;

    SELECT jsonb_build_array(jsonb_build_object(
        'versionId', quiz.version_id,
        'locale', 'zh-CN',
        'sourceCommit', quiz.source_commit,
        'sourceContentHash', quiz.source_content_hash,
        'stem', localization.stem,
        'options', (
            SELECT jsonb_object_agg(option.option_key, option_localization.option_text)
            FROM item_options AS option
            JOIN item_option_localizations AS option_localization
              ON option_localization.item_option_id = option.item_option_id
             AND option_localization.locale = 'zh-CN'
            WHERE option.learning_item_version_id = quiz.version_id
        ),
        'explanation', localization.explanation_data,
        'translationMethod', localization.translation_method,
        'translationVersion', localization.translation_version,
        'translationReviewStatus', 'approved',
        'explanationReviewStatus', 'approved',
        'reviewerId', 'integration-localization-reviewer',
        'reviewerNote', 'PostgreSQL localization integration test'
    ))
    INTO localization_payload
    FROM learning_item_localizations AS localization
    WHERE localization.learning_item_version_id = quiz.version_id
      AND localization.locale = 'zh-CN';

    released := publish_quiz_localization_batch(
        'integration-localization-publication', 'Integration zh-CN publication',
        'integration-publisher', 'integration-localization-manifest', localization_payload
    );
    IF released <> 1 THEN
        RAISE EXCEPTION 'Expected one published zh-CN Quiz';
    END IF;
    IF (SELECT count(*) FROM student_quiz_localized_bank_safe WHERE locale = 'zh-CN') <> 1 THEN
        RAISE EXCEPTION 'Published zh-CN Quiz is missing from localized student view';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM publication_readiness
        WHERE learning_item_version_id = quiz.version_id
          AND readiness_status = 'READY'
          AND blocker_codes = '[]'::jsonb
    ) THEN
        RAISE EXCEPTION 'Published Quiz is not READY';
    END IF;

    BEGIN
        PERFORM publish_quiz_batch(
            'integration-publication', 'Integration publication', 'integration-publisher',
            source_snapshot, 'integration-manifest', release_payload
        );
        RAISE EXCEPTION 'Duplicate publication unexpectedly succeeded';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;

    BEGIN
        PERFORM publish_quiz_batch(
            'integration-tampered-publication', 'Tampered publication', 'integration-publisher',
            source_snapshot, 'integration-tampered-manifest',
            jsonb_set(release_payload, '{0,answerText}', '"tampered-answer"'::jsonb)
        );
        RAISE EXCEPTION 'Tampered publication unexpectedly succeeded';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM NOT LIKE 'Release precondition failed%' THEN
            RAISE;
        END IF;
    END;
    IF EXISTS (
        SELECT 1 FROM publication_batches
        WHERE publication_batch_id = 'integration-tampered-publication'
    ) THEN
        RAISE EXCEPTION 'Failed publication left a batch record behind';
    END IF;

    SELECT correct_option_key INTO selected_key
    FROM internal_quiz_scoring_bank
    WHERE learning_item_version_id = quiz.version_id;
    IF selected_key IS DISTINCT FROM quiz.correct_option_key THEN
        RAISE EXCEPTION 'Scoring view does not expose the correct option key';
    END IF;

    INSERT INTO assessment_assignments
        (assessment_assignment_id, user_id, learning_item_version_id,
         evaluation_spec_id, knowledge_point_id, task_mode,
         selection_algorithm, selection_algorithm_version)
    SELECT
        'integration-assignment', 'integration-user', quiz.version_id,
        evaluation_spec_id, quiz.knowledge_point_id, 'diagnostic',
        'integration-selector', '1.0.0'
    FROM internal_quiz_scoring_bank
    WHERE learning_item_version_id = quiz.version_id;

    INSERT INTO task_submissions
        (submission_id, task_id, assessment_assignment_id, user_id,
         learning_item_version_id, submission_type, payload)
    VALUES
        ('integration-submission', NULL, 'integration-assignment', 'integration-user',
         quiz.version_id, 'answer', jsonb_build_object('selectedOptionKey', selected_key));

    INSERT INTO evaluation_results
        (evaluation_result_id, submission_id, evaluation_spec_id,
         evaluator_name, evaluator_version, score, is_passed, confidence,
         reason_codes, status, evaluated_at)
    SELECT
        result_id, 'integration-submission', evaluation_spec_id,
        'exact-answer', '1.0.0', 1.0, TRUE, 1.0,
        '["EXACT_ANSWER_MATCH"]'::jsonb, 'completed', now()
    FROM internal_quiz_scoring_bank
    WHERE learning_item_version_id = quiz.version_id;

    INSERT INTO assessment_evidence
        (evidence_id, user_id, learning_item_version_id, knowledge_point_id,
         answer_data, score, is_correct, evaluation_result_id, evidence_strength)
    VALUES
        ('integration-evidence', 'integration-user', quiz.version_id,
         quiz.knowledge_point_id, jsonb_build_object('selectedOptionKey', selected_key),
         1.0, TRUE, result_id, 'direct');

    UPDATE assessment_evidence
    SET task_mode = 'retrieval', is_independent = TRUE,
        is_delayed_retrieval = TRUE, scheduled_interval_days = 4
    WHERE evidence_id = 'integration-evidence';

    mastery_payload := jsonb_build_object(
        'masteryLevel', '熟悉',
        'masteryScore', 0.72,
        'memoryStatus', '延迟复测通过',
        'memoryStabilityDays', 4,
        'confidence', 0.55,
        'evidenceIds', jsonb_build_array('integration-evidence'),
        'evidenceSummary', jsonb_build_object(
            'acceptedEvidenceCount', 1,
            'effectiveEvidenceWeight', 1.15,
            'independentCorrectCount', 1,
            'delayedCorrectCount', 1,
            'delayedFailureCount', 0,
            'guidedEvidenceCount', 0
        ),
        'reasonCodes', jsonb_build_array('DELAYED_RETRIEVAL_SUCCESS'),
        'algorithmName', 'integration-rules',
        'algorithmVersion', '1.0.0',
        'nextReviewAt', '2026-08-16T00:00:00Z'
    );
    IF apply_mastery_update(
        'integration-user', quiz.knowledge_point_id, 0,
        'integration-mastery-update', mastery_payload
    ) <> 1 THEN
        RAISE EXCEPTION 'Mastery update did not create state version 1';
    END IF;
    IF apply_mastery_update(
        'integration-user', quiz.knowledge_point_id, 0,
        'integration-mastery-update', mastery_payload
    ) <> 1 THEN
        RAISE EXCEPTION 'Idempotent mastery replay returned a different version';
    END IF;
    BEGIN
        PERFORM apply_mastery_update(
            'integration-user', quiz.knowledge_point_id, 1,
            'integration-mastery-duplicate-evidence', mastery_payload
        );
        RAISE EXCEPTION 'Duplicate mastery evidence unexpectedly succeeded';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;

    BEGIN
        INSERT INTO assessment_evidence
            (evidence_id, user_id, learning_item_version_id, knowledge_point_id,
             evaluation_result_id, evidence_strength)
        VALUES
            ('integration-evidence-duplicate', 'integration-user', quiz.version_id,
             quiz.knowledge_point_id, result_id, 'direct');
        RAISE EXCEPTION 'Duplicate evidence unexpectedly succeeded';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;

    INSERT INTO api_idempotency_records
        (idempotency_record_id, actor_id, endpoint, idempotency_key,
         request_hash, processing_status)
    VALUES
        ('integration-idempotency', 'integration-user', '/assessment/submissions',
         'integration-key', 'request-hash', 'completed');

    BEGIN
        INSERT INTO api_idempotency_records
            (idempotency_record_id, actor_id, endpoint, idempotency_key,
             request_hash, processing_status)
        VALUES
            ('integration-idempotency-duplicate', 'integration-user', '/assessment/submissions',
             'integration-key', 'different-hash', 'completed');
        RAISE EXCEPTION 'Duplicate idempotency key unexpectedly succeeded';
    EXCEPTION WHEN unique_violation THEN
        NULL;
    END;

    SELECT * INTO edge FROM knowledge_edge_candidates ORDER BY edge_candidate_id LIMIT 1;
    edge_payload := jsonb_build_array(jsonb_build_object(
        'edgeCandidateId', edge.edge_candidate_id,
        'fromKnowledgePointId', edge.from_knowledge_point_id,
        'toKnowledgePointId', edge.to_knowledge_point_id,
        'relationType', edge.relation_type,
        'reviewStatus', 'approved',
        'reviewerId', 'integration-reviewer',
        'reviewerNote', 'direction checked'
    ));
    IF publish_knowledge_edge_batch(
        'integration-edge-publication', 'Integration edge publication',
        'integration-publisher', 'integration-edge-manifest', edge_payload
    ) <> 1 THEN
        RAISE EXCEPTION 'Expected one published prerequisite edge';
    END IF;
    INSERT INTO knowledge_edge_candidates (
        edge_candidate_id, from_knowledge_point_id, to_knowledge_point_id,
        relation_type, confidence, mapping_method, rationale
    ) VALUES (
        'integration-cycle-reverse', edge.to_knowledge_point_id,
        edge.from_knowledge_point_id, 'prerequisite', 0.9,
        'integration_test', 'must be rejected as a cycle'
    );
    BEGIN
        PERFORM publish_knowledge_edge_batch(
            'integration-cycle-publication', 'Cycle publication',
            'integration-publisher', 'integration-cycle-manifest',
            jsonb_build_array(jsonb_build_object(
                'edgeCandidateId', 'integration-cycle-reverse',
                'fromKnowledgePointId', edge.to_knowledge_point_id,
                'toKnowledgePointId', edge.from_knowledge_point_id,
                'relationType', 'prerequisite',
                'reviewStatus', 'approved',
                'reviewerId', 'integration-reviewer'
            ))
        );
        RAISE EXCEPTION 'Cyclic prerequisite publication unexpectedly succeeded';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM <> 'Prerequisite publication would create a cycle' THEN
            RAISE;
        END IF;
    END;
    IF EXISTS (
        SELECT 1 FROM knowledge_edges
        WHERE from_knowledge_point_id = edge.to_knowledge_point_id
          AND to_knowledge_point_id = edge.from_knowledge_point_id
          AND relation_type = 'prerequisite'
    ) THEN
        RAISE EXCEPTION 'Failed cyclic publication left a formal edge behind';
    END IF;
END
$$;

BEGIN;
SET LOCAL ROLE app_student_api;
SET LOCAL app.current_user_id = 'different-user';
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM task_submissions WHERE submission_id = 'integration-submission') THEN
        RAISE EXCEPTION 'RLS leaked another user task submission';
    ELSIF EXISTS (SELECT 1 FROM assessment_assignments WHERE assessment_assignment_id = 'integration-assignment') THEN
        RAISE EXCEPTION 'RLS leaked another user assignment';
    ELSIF EXISTS (SELECT 1 FROM evaluation_results WHERE evaluation_result_id = 'integration-result') THEN
        RAISE EXCEPTION 'RLS leaked another user result';
    ELSIF EXISTS (SELECT 1 FROM api_idempotency_records WHERE idempotency_record_id = 'integration-idempotency') THEN
        RAISE EXCEPTION 'RLS leaked another user idempotency record';
    ELSIF EXISTS (SELECT 1 FROM student_knowledge_status_safe WHERE user_id = 'integration-user') THEN
        RAISE EXCEPTION 'Safe view leaked another user mastery state';
    ELSIF EXISTS (SELECT 1 FROM student_mastery_history_safe WHERE user_id = 'integration-user') THEN
        RAISE EXCEPTION 'Safe view leaked another user mastery history';
    END IF;
END
$$;
ROLLBACK;

BEGIN;
SET LOCAL ROLE app_student_api;
SET LOCAL app.current_user_id = 'integration-user';
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM task_submissions WHERE submission_id = 'integration-submission')
       OR NOT EXISTS (SELECT 1 FROM assessment_assignments WHERE assessment_assignment_id = 'integration-assignment')
       OR NOT EXISTS (SELECT 1 FROM evaluation_results WHERE evaluation_result_id = 'integration-result')
       OR NOT EXISTS (SELECT 1 FROM api_idempotency_records WHERE idempotency_record_id = 'integration-idempotency')
       OR NOT EXISTS (SELECT 1 FROM student_knowledge_status_safe WHERE user_id = 'integration-user')
       OR NOT EXISTS (SELECT 1 FROM student_mastery_history_safe WHERE user_id = 'integration-user') THEN
        RAISE EXCEPTION 'RLS hid the authenticated user assessment data';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM get_student_quiz_feedback('integration-submission', 'zh-CN')
        WHERE locale = 'zh-CN' AND fallback_used = FALSE
    ) THEN
        RAISE EXCEPTION 'Completed submission cannot read published zh-CN explanation';
    END IF;
    IF EXISTS (SELECT 1 FROM get_student_quiz_feedback('missing-submission', 'zh-CN')) THEN
        RAISE EXCEPTION 'Feedback function returned content without a completed owned submission';
    END IF;
END
$$;
ROLLBACK;

SELECT 'PostgreSQL integration passed' AS result;
