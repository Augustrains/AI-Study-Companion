-- Runtime hardening: safe practice views, assessment assignments, idempotency,
-- strict publication readiness, and an atomic controlled Quiz publisher.
-- Apply after 003_content_governance.sql and before generated seeds.

BEGIN;

CREATE TABLE IF NOT EXISTS assessment_assignments (
    assessment_assignment_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    diagnostic_id TEXT REFERENCES diagnostic_attempts(diagnostic_id),
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    evaluation_spec_id TEXT NOT NULL REFERENCES evaluation_specs(evaluation_spec_id),
    knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    task_mode TEXT NOT NULL CHECK (task_mode IN (
        'diagnostic', 'guided_practice', 'independent', 'retrieval', 'remediation', 'challenge'
    )),
    status TEXT NOT NULL DEFAULT 'offered'
        CHECK (status IN ('offered', 'submitted', 'expired', 'cancelled')),
    selection_algorithm TEXT NOT NULL,
    selection_algorithm_version TEXT NOT NULL,
    selection_reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    selection_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    offered_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ,
    submitted_at TIMESTAMPTZ
);

ALTER TABLE task_submissions
    ALTER COLUMN task_id DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS assessment_assignment_id TEXT
        REFERENCES assessment_assignments(assessment_assignment_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'task_submissions_exactly_one_context'
    ) THEN
        ALTER TABLE task_submissions
            ADD CONSTRAINT task_submissions_exactly_one_context
            CHECK (num_nonnulls(task_id, assessment_assignment_id) = 1);
    END IF;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_task_submissions_assignment
    ON task_submissions(assessment_assignment_id)
    WHERE assessment_assignment_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS api_idempotency_records (
    idempotency_record_id TEXT PRIMARY KEY,
    actor_id TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    processing_status TEXT NOT NULL DEFAULT 'processing'
        CHECK (processing_status IN ('processing', 'completed', 'failed')),
    response_status INTEGER,
    response_body JSONB,
    resource_type TEXT,
    resource_id TEXT,
    locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (actor_id, endpoint, idempotency_key)
);

CREATE TABLE IF NOT EXISTS knowledge_edge_candidates (
    edge_candidate_id TEXT PRIMARY KEY,
    from_knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    to_knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    relation_type TEXT NOT NULL DEFAULT 'prerequisite'
        CHECK (relation_type IN ('prerequisite', 'related', 'contains', 'extends')),
    confidence NUMERIC(5, 4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    mapping_method TEXT NOT NULL,
    rationale TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'superseded')),
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (from_knowledge_point_id <> to_knowledge_point_id),
    UNIQUE (from_knowledge_point_id, to_knowledge_point_id, relation_type)
);

CREATE TABLE IF NOT EXISTS learning_item_enrichment_candidates (
    enrichment_candidate_id TEXT PRIMARY KEY,
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    enrichment_type TEXT NOT NULL
        CHECK (enrichment_type IN ('difficulty', 'estimated_minutes', 'explanation')),
    candidate_value JSONB NOT NULL,
    confidence NUMERIC(5, 4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    generation_method TEXT NOT NULL,
    generation_version TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'superseded')),
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS learning_item_localizations (
    learning_item_localization_id TEXT PRIMARY KEY,
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    locale TEXT NOT NULL,
    stem TEXT NOT NULL,
    explanation TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'needs_review', 'approved', 'published', 'rejected')),
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (learning_item_version_id, locale)
);

CREATE TABLE IF NOT EXISTS item_quality_statistics (
    learning_item_version_id TEXT PRIMARY KEY REFERENCES learning_item_versions(learning_item_version_id),
    exposure_count BIGINT NOT NULL DEFAULT 0 CHECK (exposure_count >= 0),
    submission_count BIGINT NOT NULL DEFAULT 0 CHECK (submission_count >= 0),
    correct_count BIGINT NOT NULL DEFAULT 0 CHECK (correct_count >= 0),
    skip_count BIGINT NOT NULL DEFAULT 0 CHECK (skip_count >= 0),
    average_response_time_ms NUMERIC(12, 2),
    empirical_difficulty NUMERIC(7, 6)
        CHECK (empirical_difficulty IS NULL OR empirical_difficulty BETWEEN 0 AND 1),
    discrimination NUMERIC(8, 4),
    sample_status TEXT NOT NULL DEFAULT 'insufficient'
        CHECK (sample_status IN ('insufficient', 'provisional', 'stable')),
    statistics_version TEXT NOT NULL DEFAULT 'v1',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (correct_count <= submission_count)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_assessment_evidence_evaluation_result
    ON assessment_evidence(evaluation_result_id)
    WHERE evaluation_result_id IS NOT NULL;

ALTER TABLE content_review_batches
    ADD COLUMN IF NOT EXISTS manifest_hash TEXT;

ALTER TABLE publication_batches
    ADD COLUMN IF NOT EXISTS source_commit_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS manifest_hash TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_publication_batches_manifest_hash
    ON publication_batches(manifest_hash)
    WHERE manifest_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_assignments_user_status
    ON assessment_assignments(user_id, status, offered_at DESC);
CREATE INDEX IF NOT EXISTS idx_assignments_item
    ON assessment_assignments(learning_item_version_id, offered_at DESC);
CREATE INDEX IF NOT EXISTS idx_idempotency_created
    ON api_idempotency_records(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_edge_candidates_status
    ON knowledge_edge_candidates(status, from_knowledge_point_id);
CREATE INDEX IF NOT EXISTS idx_enrichment_candidates_status
    ON learning_item_enrichment_candidates(status, enrichment_type);
CREATE INDEX IF NOT EXISTS idx_localizations_locale_status
    ON learning_item_localizations(locale, status);

-- Replace the old internal practice view with a published, student-safe view.
DROP VIEW IF EXISTS practice_task_bank;
DROP VIEW IF EXISTS student_practice_task_bank_safe;
DROP VIEW IF EXISTS internal_practice_task_bank;

CREATE VIEW student_practice_task_bank_safe AS
SELECT
    item.learning_item_id,
    version.learning_item_version_id,
    item.item_type,
    item.title,
    item.language,
    item.evaluation_mode,
    document.source_id,
    document.source_url,
    version.stem
FROM learning_items AS item
JOIN learning_item_versions AS version
  ON version.learning_item_version_id = item.current_version_id
JOIN source_documents AS document
  ON document.source_document_id = item.source_document_id
WHERE item.assessment_eligible = FALSE
  AND item.item_type <> 'quiz_question'
  AND item.status = 'published'
  AND document.source_id IN ('microsoft-ml-for-beginners', 'microsoft-ai-for-beginners')
  AND EXISTS (
      SELECT 1 FROM evaluation_specs AS spec
      WHERE spec.learning_item_version_id = version.learning_item_version_id
        AND spec.status = 'published'
  );

CREATE VIEW practice_task_bank AS
SELECT * FROM student_practice_task_bank_safe;

CREATE VIEW internal_practice_task_bank AS
SELECT
    item.learning_item_id,
    version.learning_item_version_id,
    item.item_type,
    item.title,
    item.language,
    item.evaluation_mode,
    item.status,
    document.source_id,
    document.source_url,
    version.stem,
    version.answer_data,
    version.explanation,
    spec.evaluation_spec_id,
    spec.config AS evaluation_config,
    spec.evidence_policy,
    spec.status AS evaluation_status
FROM learning_items AS item
JOIN learning_item_versions AS version
  ON version.learning_item_version_id = item.current_version_id
JOIN source_documents AS document
  ON document.source_document_id = item.source_document_id
JOIN evaluation_specs AS spec
  ON spec.learning_item_version_id = version.learning_item_version_id
WHERE item.assessment_eligible = FALSE
  AND item.item_type <> 'quiz_question'
  AND document.source_id IN ('microsoft-ml-for-beginners', 'microsoft-ai-for-beginners');

-- Rebuild readiness with exact Quiz requirements and all blocker codes.
DROP VIEW IF EXISTS publication_readiness;
DROP VIEW IF EXISTS content_review_queue;

CREATE VIEW content_review_queue AS
SELECT
    item.learning_item_id,
    version.learning_item_version_id,
    item.item_type,
    item.status AS item_status,
    item.evaluation_mode,
    document.source_id,
    document.source_url,
    document.content_version AS source_commit,
    document.content_hash AS source_content_hash,
    version.stem,
    version.answer_data,
    version.explanation,
    (version.answer_data ? 'answer'
      AND length(btrim(COALESCE(version.answer_data ->> 'answer', ''))) > 0) AS has_answer,
    (SELECT count(*) FROM item_options AS option
     WHERE option.learning_item_version_id = version.learning_item_version_id
       AND option.is_correct = TRUE) AS correct_option_count,
    (SELECT count(*) FROM item_knowledge_maps AS mapping
     WHERE mapping.learning_item_version_id = version.learning_item_version_id
       AND mapping.relation_type = 'target') AS approved_target_mapping_count,
    (SELECT count(*) FROM item_knowledge_map_candidates AS candidate
     WHERE candidate.learning_item_version_id = version.learning_item_version_id
       AND candidate.relation_type = 'target'
       AND candidate.status = 'pending') AS pending_target_mapping_count,
    EXISTS (
        SELECT 1 FROM question_review_records AS review
        WHERE review.learning_item_version_id = version.learning_item_version_id
          AND review.review_status = 'approved'
          AND review.checked_answer = TRUE
          AND review.checked_mapping = TRUE
          AND review.checked_source = TRUE
    ) AS content_review_approved,
    EXISTS (
        SELECT 1 FROM evaluation_specs AS spec
        WHERE spec.learning_item_version_id = version.learning_item_version_id
          AND spec.evaluation_mode = 'exact_answer'
          AND spec.status = 'published'
    ) AS exact_evaluation_published
FROM learning_items AS item
JOIN learning_item_versions AS version
  ON version.learning_item_version_id = item.current_version_id
JOIN source_documents AS document
  ON document.source_document_id = item.source_document_id;

CREATE VIEW publication_readiness AS
SELECT
    queue.*,
    blockers.blocker_codes,
    CASE
        WHEN jsonb_array_length(blockers.blocker_codes) = 0 THEN 'READY'
        ELSE blockers.blocker_codes ->> 0
    END AS readiness_status
FROM content_review_queue AS queue
CROSS JOIN LATERAL (
    SELECT to_jsonb(array_remove(ARRAY[
        CASE WHEN queue.source_id NOT IN (
            'microsoft-ml-for-beginners', 'microsoft-ai-for-beginners'
        ) THEN 'BLOCKED_SOURCE' END,
        CASE WHEN queue.item_type = 'quiz_question' AND NOT queue.has_answer
            THEN 'BLOCKED_ANSWER' END,
        CASE WHEN queue.item_type = 'quiz_question' AND queue.correct_option_count <> 1
            THEN 'BLOCKED_CORRECT_OPTION_COUNT' END,
        CASE WHEN queue.approved_target_mapping_count = 0
            THEN 'BLOCKED_TARGET_MAPPING' END,
        CASE WHEN NOT queue.content_review_approved
            THEN 'BLOCKED_REVIEW' END,
        CASE WHEN queue.item_type = 'quiz_question' AND NOT queue.exact_evaluation_published
            THEN 'BLOCKED_EXACT_EVALUATION' END
    ]::text[], NULL)) AS blocker_codes
) AS blockers;

-- Make the Quiz scoring contract unambiguous and keep it restricted to the
-- approved sources and formally published target mappings.
DROP VIEW IF EXISTS internal_quiz_scoring_bank;

CREATE VIEW internal_quiz_scoring_bank AS
SELECT
    item.learning_item_id,
    version.learning_item_version_id,
    spec.evaluation_spec_id,
    (SELECT option.option_key
     FROM item_options AS option
     WHERE option.learning_item_version_id = version.learning_item_version_id
       AND option.is_correct = TRUE
     ORDER BY option.sort_order
     LIMIT 1) AS correct_option_key,
    version.answer_data,
    spec.config AS evaluation_config,
    COALESCE((
        SELECT jsonb_agg(
            jsonb_build_object(
                'key', option.option_key,
                'text', option.option_text,
                'isCorrect', option.is_correct
            ) ORDER BY option.sort_order
        )
        FROM item_options AS option
        WHERE option.learning_item_version_id = version.learning_item_version_id
    ), '[]'::jsonb) AS options
FROM learning_items AS item
JOIN learning_item_versions AS version
  ON version.learning_item_version_id = item.current_version_id
JOIN source_documents AS document
  ON document.source_document_id = item.source_document_id
JOIN evaluation_specs AS spec
  ON spec.learning_item_version_id = version.learning_item_version_id
 AND spec.evaluation_mode = 'exact_answer'
 AND spec.status = 'published'
WHERE item.item_type = 'quiz_question'
  AND item.assessment_eligible = TRUE
  AND item.status = 'published'
  AND document.source_id IN ('microsoft-ml-for-beginners', 'microsoft-ai-for-beginners')
  AND (SELECT count(*) FROM item_options AS option
       WHERE option.learning_item_version_id = version.learning_item_version_id
         AND option.is_correct = TRUE) = 1
  AND EXISTS (
      SELECT 1 FROM item_knowledge_maps AS mapping
      WHERE mapping.learning_item_version_id = version.learning_item_version_id
        AND mapping.relation_type = 'target'
  );

-- Only this SECURITY DEFINER function may perform final Quiz publication for
-- the runtime publisher role. It validates source commits, reviewed content,
-- exact answers, target mapping candidates, and a unique release manifest.
CREATE OR REPLACE FUNCTION publish_quiz_batch(
    p_publication_batch_id TEXT,
    p_batch_name TEXT,
    p_actor TEXT,
    p_source_commit_snapshot JSONB,
    p_manifest_hash TEXT,
    p_items JSONB
) RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    item_payload JSONB;
    evaluation_id TEXT;
    published_count INTEGER := 0;
    v_review_batch_id TEXT := 'review-' || p_publication_batch_id;
BEGIN
    IF length(btrim(COALESCE(p_publication_batch_id, ''))) = 0
       OR length(btrim(COALESCE(p_batch_name, ''))) = 0
       OR length(btrim(COALESCE(p_actor, ''))) = 0
       OR length(btrim(COALESCE(p_manifest_hash, ''))) = 0 THEN
        RAISE EXCEPTION 'Publication identifiers, actor, and manifest hash are required';
    END IF;
    IF jsonb_typeof(p_items) <> 'array' OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'Publication items must be a non-empty JSON array';
    END IF;
    IF jsonb_typeof(p_source_commit_snapshot) <> 'object'
       OR p_source_commit_snapshot = '{}'::jsonb THEN
        RAISE EXCEPTION 'Source commit snapshot must be a non-empty JSON object';
    END IF;
    IF jsonb_array_length(p_items) <> (
        SELECT count(DISTINCT value ->> 'versionId')
        FROM jsonb_array_elements(p_items)
    ) THEN
        RAISE EXCEPTION 'Publication payload contains duplicate versionId values';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtext(p_publication_batch_id));
    IF EXISTS (
        SELECT 1 FROM publication_batches
        WHERE publication_batch_id = p_publication_batch_id
    ) THEN
        RAISE EXCEPTION 'Publication batch ID already exists: %', p_publication_batch_id
            USING ERRCODE = '23505';
    END IF;
    IF EXISTS (
        SELECT 1 FROM publication_batches
        WHERE manifest_hash = p_manifest_hash
    ) THEN
        RAISE EXCEPTION 'Publication manifest has already been used: %', p_manifest_hash
            USING ERRCODE = '23505';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM jsonb_each_text(p_source_commit_snapshot) AS expected(source_id, commit_sha)
        WHERE expected.source_id NOT IN (
            'microsoft-ml-for-beginners', 'microsoft-ai-for-beginners'
        ) OR NOT EXISTS (
            SELECT 1 FROM source_repositories AS repository
            WHERE repository.source_id = expected.source_id
              AND repository.commit_sha = expected.commit_sha
        )
    ) THEN
        RAISE EXCEPTION 'Source commit snapshot does not match the database';
    END IF;

    INSERT INTO content_review_batches
        (review_batch_id, batch_name, source_commit_snapshot, manifest_hash, status, created_by)
    VALUES
        (v_review_batch_id, p_batch_name, p_source_commit_snapshot, p_manifest_hash, 'in_review', p_actor);

    INSERT INTO publication_batches
        (publication_batch_id, batch_name, status, requested_by, validated_by,
         validation_report, source_commit_snapshot, manifest_hash, validated_at)
    VALUES
        (p_publication_batch_id, p_batch_name, 'validated', p_actor, p_actor,
         jsonb_build_object(
             'approvedItemCount', jsonb_array_length(p_items),
             'generator', 'review_release.py',
             'databaseSessionUser', session_user
         ), p_source_commit_snapshot, p_manifest_hash, now());

    FOR item_payload IN SELECT value FROM jsonb_array_elements(p_items)
    LOOP
        IF length(btrim(COALESCE(item_payload ->> 'reviewerId', ''))) = 0 THEN
            RAISE EXCEPTION 'Every publication item requires reviewerId';
        END IF;

        SELECT spec.evaluation_spec_id
        INTO evaluation_id
        FROM learning_items AS item
        JOIN learning_item_versions AS version
          ON version.learning_item_version_id = item.current_version_id
        JOIN source_documents AS document
          ON document.source_document_id = item.source_document_id
        JOIN source_repositories AS repository
          ON repository.source_id = document.source_id
        JOIN evaluation_specs AS spec
          ON spec.learning_item_version_id = version.learning_item_version_id
         AND spec.evaluation_mode = 'exact_answer'
        JOIN item_knowledge_map_candidates AS candidate
          ON candidate.learning_item_version_id = version.learning_item_version_id
         AND candidate.relation_type = 'target'
        WHERE item.learning_item_id = item_payload ->> 'itemId'
          AND version.learning_item_version_id = item_payload ->> 'versionId'
          AND item.item_type = 'quiz_question'
          AND item.assessment_eligible = TRUE
          AND item.status IN ('needs_review', 'approved')
          AND document.source_id = item_payload ->> 'sourceId'
          AND document.content_version = item_payload ->> 'sourceCommit'
          AND document.content_hash = item_payload ->> 'sourceContentHash'
          AND repository.commit_sha = item_payload ->> 'sourceCommit'
          AND p_source_commit_snapshot ->> document.source_id = document.content_version
          AND version.stem = item_payload ->> 'questionStem'
          AND version.answer_data ->> 'answer' = item_payload ->> 'answerText'
          AND candidate.mapping_candidate_id = item_payload ->> 'candidateId'
          AND candidate.knowledge_point_id = item_payload ->> 'knowledgePointId'
          AND candidate.status IN ('pending', 'approved')
          AND (SELECT count(*) FROM item_options AS option
               WHERE option.learning_item_version_id = version.learning_item_version_id
                 AND option.is_correct = TRUE) = 1
          AND (SELECT option.option_key FROM item_options AS option
               WHERE option.learning_item_version_id = version.learning_item_version_id
                 AND option.is_correct = TRUE
               LIMIT 1) = item_payload ->> 'correctOptionKey'
        ORDER BY spec.spec_version DESC
        LIMIT 1;

        IF evaluation_id IS NULL THEN
            RAISE EXCEPTION 'Release precondition failed for version %', item_payload ->> 'versionId';
        END IF;

        UPDATE item_knowledge_map_candidates
        SET status = 'approved',
            reviewed_by = item_payload ->> 'reviewerId',
            reviewed_at = now()
        WHERE mapping_candidate_id = item_payload ->> 'candidateId';

        INSERT INTO item_knowledge_maps
            (learning_item_version_id, knowledge_point_id, relation_type,
             weight, mapping_confidence, mapping_method)
        VALUES
            (item_payload ->> 'versionId', item_payload ->> 'knowledgePointId', 'target', 1.0,
             (item_payload ->> 'mappingConfidence')::numeric,
             'human_approved_upstream_quiz_group')
        ON CONFLICT (learning_item_version_id, knowledge_point_id, relation_type)
        DO UPDATE SET
            mapping_confidence = EXCLUDED.mapping_confidence,
            mapping_method = EXCLUDED.mapping_method;

        INSERT INTO question_review_records
            (review_id, learning_item_version_id, reviewer_id, review_status,
             review_note, checked_answer, checked_mapping, checked_source)
        VALUES
            ('question-review-' || md5((item_payload ->> 'versionId') || chr(31) || p_publication_batch_id),
             item_payload ->> 'versionId', item_payload ->> 'reviewerId', 'approved',
             item_payload ->> 'reviewerNote', TRUE, TRUE, TRUE);

        INSERT INTO content_review_batch_items
            (review_batch_id, learning_item_version_id, review_status,
             reviewer_id, review_note, reviewed_at)
        VALUES
            (v_review_batch_id, item_payload ->> 'versionId', 'approved',
             item_payload ->> 'reviewerId', item_payload ->> 'reviewerNote', now());

        UPDATE knowledge_nodes
        SET status = 'active'
        WHERE knowledge_point_id = item_payload ->> 'knowledgePointId';

        UPDATE evaluation_specs
        SET status = 'published', approved_by = item_payload ->> 'reviewerId', approved_at = now()
        WHERE evaluation_spec_id = evaluation_id;

        UPDATE learning_items
        SET status = 'published', updated_at = now()
        WHERE learning_item_id = item_payload ->> 'itemId'
          AND current_version_id = item_payload ->> 'versionId';

        UPDATE task_templates
        SET status = 'published'
        WHERE learning_item_id = item_payload ->> 'itemId'
          AND task_version_id = item_payload ->> 'versionId'
          AND status IN ('draft', 'approved');

        INSERT INTO publication_batch_items
            (publication_batch_id, learning_item_version_id, evaluation_spec_id,
             publish_status, blocker_codes, published_at)
        VALUES
            (p_publication_batch_id, item_payload ->> 'versionId', evaluation_id,
             'published', '[]'::jsonb, now());

        published_count := published_count + 1;
        evaluation_id := NULL;
    END LOOP;

    UPDATE content_review_batches
    SET status = 'completed', completed_at = now()
    WHERE content_review_batches.review_batch_id = v_review_batch_id;

    UPDATE publication_batches
    SET status = 'published', published_by = p_actor, published_at = now()
    WHERE publication_batch_id = p_publication_batch_id
      AND status = 'validated';

    RETURN published_count;
END
$$;

REVOKE ALL ON FUNCTION publish_quiz_batch(TEXT, TEXT, TEXT, JSONB, TEXT, JSONB) FROM PUBLIC;

COMMIT;
