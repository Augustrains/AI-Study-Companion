-- Algorithm-safe read models, mastery state governance, and prerequisite release.
-- Apply after 007_localization_roles.sql.

BEGIN;

ALTER TABLE assessment_evidence
    ADD COLUMN IF NOT EXISTS task_mode TEXT
        CHECK (task_mode IS NULL OR task_mode IN (
            'diagnostic', 'guided_practice', 'independent', 'retrieval',
            'remediation', 'challenge'
        )),
    ADD COLUMN IF NOT EXISTS is_independent BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_delayed_retrieval BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS scheduled_interval_days NUMERIC(10, 4)
        CHECK (scheduled_interval_days IS NULL OR scheduled_interval_days >= 0),
    ADD COLUMN IF NOT EXISTS evidence_context JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE assessment_evidence
    DROP CONSTRAINT IF EXISTS assessment_evidence_score_range,
    DROP CONSTRAINT IF EXISTS assessment_evidence_response_time_nonnegative,
    DROP CONSTRAINT IF EXISTS assessment_evidence_hint_count_nonnegative,
    DROP CONSTRAINT IF EXISTS assessment_evidence_retry_count_nonnegative,
    DROP CONSTRAINT IF EXISTS assessment_evidence_confidence_before_range,
    DROP CONSTRAINT IF EXISTS assessment_evidence_confidence_after_range;
ALTER TABLE assessment_evidence
    ADD CONSTRAINT assessment_evidence_score_range
        CHECK (score IS NULL OR score BETWEEN 0 AND 1),
    ADD CONSTRAINT assessment_evidence_response_time_nonnegative
        CHECK (response_time_ms IS NULL OR response_time_ms >= 0),
    ADD CONSTRAINT assessment_evidence_hint_count_nonnegative CHECK (hint_count >= 0),
    ADD CONSTRAINT assessment_evidence_retry_count_nonnegative CHECK (retry_count >= 0),
    ADD CONSTRAINT assessment_evidence_confidence_before_range
        CHECK (confidence_before IS NULL OR confidence_before BETWEEN 0 AND 1),
    ADD CONSTRAINT assessment_evidence_confidence_after_range
        CHECK (confidence_after IS NULL OR confidence_after BETWEEN 0 AND 1);

ALTER TABLE ai_assessments DROP CONSTRAINT IF EXISTS ai_assessments_level_check;
ALTER TABLE ai_assessments
    ADD CONSTRAINT ai_assessments_level_check
        CHECK (level IN ('未评测', '不会', '了解', '熟悉', '掌握')),
    DROP CONSTRAINT IF EXISTS ai_assessments_confidence_range;
ALTER TABLE ai_assessments
    ADD CONSTRAINT ai_assessments_confidence_range
        CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1);

ALTER TABLE learner_mastery_current
    ADD COLUMN IF NOT EXISTS mastery_level TEXT NOT NULL DEFAULT '未评测'
        CHECK (mastery_level IN ('未评测', '不会', '了解', '熟悉', '掌握')),
    ADD COLUMN IF NOT EXISTS memory_status TEXT NOT NULL DEFAULT '未验证'
        CHECK (memory_status IN ('未验证', '首次验证', '延迟复测通过', '稳定保持')),
    ADD COLUMN IF NOT EXISTS evidence_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS algorithm_name TEXT,
    ADD COLUMN IF NOT EXISTS algorithm_version TEXT,
    ADD COLUMN IF NOT EXISTS reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS last_evidence_id TEXT REFERENCES assessment_evidence(evidence_id);

ALTER TABLE learner_mastery_current
    DROP CONSTRAINT IF EXISTS learner_mastery_score_range,
    DROP CONSTRAINT IF EXISTS learner_mastery_stability_nonnegative,
    DROP CONSTRAINT IF EXISTS learner_mastery_confidence_range,
    DROP CONSTRAINT IF EXISTS learner_mastery_state_version_positive;
ALTER TABLE learner_mastery_current
    ADD CONSTRAINT learner_mastery_score_range CHECK (mastery_score BETWEEN 0 AND 1),
    ADD CONSTRAINT learner_mastery_stability_nonnegative
        CHECK (memory_stability_days IS NULL OR memory_stability_days >= 0),
    ADD CONSTRAINT learner_mastery_confidence_range
        CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    ADD CONSTRAINT learner_mastery_state_version_positive CHECK (state_version > 0);

CREATE TABLE IF NOT EXISTS learner_mastery_history (
    mastery_history_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    previous_mastery_level TEXT
        CHECK (previous_mastery_level IS NULL OR previous_mastery_level IN
            ('未评测', '不会', '了解', '熟悉', '掌握')),
    new_mastery_level TEXT NOT NULL
        CHECK (new_mastery_level IN ('未评测', '不会', '了解', '熟悉', '掌握')),
    previous_mastery_score NUMERIC(8, 4)
        CHECK (previous_mastery_score IS NULL OR previous_mastery_score BETWEEN 0 AND 1),
    new_mastery_score NUMERIC(8, 4) NOT NULL CHECK (new_mastery_score BETWEEN 0 AND 1),
    previous_memory_status TEXT
        CHECK (previous_memory_status IS NULL OR previous_memory_status IN
            ('未验证', '首次验证', '延迟复测通过', '稳定保持')),
    new_memory_status TEXT NOT NULL
        CHECK (new_memory_status IN ('未验证', '首次验证', '延迟复测通过', '稳定保持')),
    previous_memory_stability_days NUMERIC(10, 4)
        CHECK (previous_memory_stability_days IS NULL OR previous_memory_stability_days >= 0),
    new_memory_stability_days NUMERIC(10, 4)
        CHECK (new_memory_stability_days IS NULL OR new_memory_stability_days >= 0),
    confidence NUMERIC(5, 4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    algorithm_name TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    state_version INTEGER NOT NULL CHECK (state_version > 0),
    next_review_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, knowledge_point_id, state_version)
);

CREATE TABLE IF NOT EXISTS mastery_evidence_processing (
    evidence_id TEXT PRIMARY KEY REFERENCES assessment_evidence(evidence_id),
    mastery_history_id TEXT NOT NULL REFERENCES learner_mastery_history(mastery_history_id),
    algorithm_name TEXT NOT NULL,
    algorithm_version TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_edge_review_records (
    edge_review_id TEXT PRIMARY KEY,
    edge_candidate_id TEXT NOT NULL REFERENCES knowledge_edge_candidates(edge_candidate_id),
    reviewer_id TEXT NOT NULL,
    review_status TEXT NOT NULL CHECK (review_status IN ('approved', 'changes_requested', 'rejected')),
    review_note TEXT,
    checked_direction BOOLEAN NOT NULL DEFAULT FALSE,
    checked_cycle BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS knowledge_edge_publication_batches (
    edge_publication_batch_id TEXT PRIMARY KEY,
    batch_name TEXT NOT NULL,
    requested_by TEXT NOT NULL,
    manifest_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('published', 'failed', 'cancelled')),
    validation_report JSONB NOT NULL DEFAULT '{}'::jsonb,
    published_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS knowledge_edge_publication_batch_items (
    edge_publication_batch_id TEXT NOT NULL
        REFERENCES knowledge_edge_publication_batches(edge_publication_batch_id),
    edge_candidate_id TEXT NOT NULL REFERENCES knowledge_edge_candidates(edge_candidate_id),
    from_knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    to_knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    relation_type TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (edge_publication_batch_id, edge_candidate_id)
);

CREATE INDEX IF NOT EXISTS idx_mastery_history_user_knowledge_time
    ON learner_mastery_history(user_id, knowledge_point_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_mastery_history_evidence_ids
    ON learner_mastery_history USING gin(evidence_ids);
CREATE INDEX IF NOT EXISTS idx_mastery_next_review
    ON learner_mastery_current(next_review_at) WHERE next_review_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_edge_reviews_candidate_time
    ON knowledge_edge_review_records(edge_candidate_id, created_at DESC);

-- Read-only algorithm catalog. It includes no answer_data, correct flags,
-- hidden tests, submission payloads, or localized post-answer explanations.
CREATE OR REPLACE VIEW algorithm_knowledge_catalog AS
SELECT
    node.knowledge_point_id,
    node.knowledge_point_name,
    node.description,
    node.node_level,
    node.status,
    ability.ability_id,
    ability.ability_name,
    chapter.chapter_id,
    chapter.chapter_name,
    chapter.sort_order,
    book.book_id,
    book.book_name
FROM knowledge_nodes AS node
LEFT JOIN abilities AS ability ON ability.ability_id = node.ability_id
LEFT JOIN chapters AS chapter ON chapter.chapter_id = node.chapter_id
LEFT JOIN books AS book ON book.book_id = chapter.book_id
WHERE node.status = 'active';

CREATE OR REPLACE VIEW algorithm_question_catalog AS
SELECT
    item.learning_item_id,
    version.learning_item_version_id,
    item.item_type,
    item.title,
    item.language,
    item.evaluation_mode,
    item.assessment_eligible,
    document.source_id,
    document.source_url,
    version.stem,
    version.estimated_minutes,
    version.difficulty,
    spec.evidence_policy,
    COALESCE(
        jsonb_agg(DISTINCT jsonb_build_object(
            'knowledgePointId', mapping.knowledge_point_id,
            'relationType', mapping.relation_type,
            'weight', mapping.weight
        )) FILTER (WHERE mapping.knowledge_point_id IS NOT NULL),
        '[]'::jsonb
    ) AS knowledge_mappings,
    statistics.exposure_count,
    statistics.submission_count,
    statistics.empirical_difficulty,
    statistics.discrimination,
    statistics.sample_status
FROM learning_items AS item
JOIN learning_item_versions AS version
  ON version.learning_item_version_id = item.current_version_id
JOIN source_documents AS document ON document.source_document_id = item.source_document_id
JOIN evaluation_specs AS spec
  ON spec.learning_item_version_id = version.learning_item_version_id
 AND spec.status = 'published'
LEFT JOIN item_knowledge_maps AS mapping
  ON mapping.learning_item_version_id = version.learning_item_version_id
LEFT JOIN item_quality_statistics AS statistics
  ON statistics.learning_item_version_id = version.learning_item_version_id
WHERE item.status = 'published'
  AND document.source_id IN ('microsoft-ml-for-beginners', 'microsoft-ai-for-beginners')
GROUP BY item.learning_item_id, version.learning_item_version_id,
    document.source_id, document.source_url, spec.evidence_policy,
    statistics.learning_item_version_id;

CREATE OR REPLACE VIEW algorithm_prerequisite_graph AS
SELECT
    edge.from_knowledge_point_id,
    source.knowledge_point_name AS from_knowledge_point_name,
    edge.to_knowledge_point_id,
    target.knowledge_point_name AS to_knowledge_point_name,
    edge.relation_type,
    edge.weight
FROM knowledge_edges AS edge
JOIN knowledge_nodes AS source
  ON source.knowledge_point_id = edge.from_knowledge_point_id
JOIN knowledge_nodes AS target
  ON target.knowledge_point_id = edge.to_knowledge_point_id
WHERE edge.relation_type = 'prerequisite'
  AND source.status = 'active'
  AND target.status = 'active';

CREATE OR REPLACE VIEW algorithm_evidence_feed AS
SELECT
    evidence.evidence_id,
    evidence.user_id,
    evidence.knowledge_point_id,
    evidence.learning_item_version_id,
    evidence.evaluation_result_id,
    evidence.evidence_strength,
    COALESCE(evidence.task_mode, assignment.task_mode) AS task_mode,
    evidence.score,
    evidence.is_correct,
    evidence.response_time_ms,
    evidence.hint_count,
    evidence.retry_count,
    evidence.confidence_before,
    evidence.confidence_after,
    evidence.error_type,
    evidence.is_independent,
    evidence.is_delayed_retrieval,
    evidence.scheduled_interval_days,
    evidence.evidence_version,
    evidence.occurred_at,
    processing.processed_at
FROM assessment_evidence AS evidence
LEFT JOIN evaluation_results AS result
  ON result.evaluation_result_id = evidence.evaluation_result_id
LEFT JOIN task_submissions AS submission
  ON submission.submission_id = result.submission_id
LEFT JOIN assessment_assignments AS assignment
  ON assignment.assessment_assignment_id = submission.assessment_assignment_id
LEFT JOIN mastery_evidence_processing AS processing
  ON processing.evidence_id = evidence.evidence_id
WHERE evidence.evidence_strength <> 'none'
  AND evidence.score IS NOT NULL
  AND evidence.knowledge_point_id IS NOT NULL
  AND COALESCE(evidence.task_mode, assignment.task_mode) IS NOT NULL;

CREATE OR REPLACE VIEW algorithm_learner_state AS
SELECT
    state.user_id,
    state.knowledge_point_id,
    node.knowledge_point_name,
    state.mastery_level,
    state.mastery_score,
    state.memory_status,
    state.memory_stability_days,
    state.confidence,
    state.evidence_summary,
    state.reason_codes,
    state.last_evidence_id,
    state.last_evidence_at,
    state.next_review_at,
    state.algorithm_name,
    state.algorithm_version,
    state.state_version,
    state.updated_at
FROM learner_mastery_current AS state
JOIN knowledge_nodes AS node ON node.knowledge_point_id = state.knowledge_point_id;

CREATE OR REPLACE VIEW student_knowledge_status_safe AS
SELECT
    state.user_id,
    state.knowledge_point_id,
    node.knowledge_point_name,
    state.mastery_level,
    state.mastery_score,
    state.memory_status,
    state.memory_stability_days,
    state.confidence,
    state.reason_codes,
    state.last_evidence_at,
    state.next_review_at,
    state.state_version,
    state.updated_at
FROM learner_mastery_current AS state
JOIN knowledge_nodes AS node ON node.knowledge_point_id = state.knowledge_point_id
WHERE state.user_id = current_setting('app.current_user_id', TRUE);

CREATE OR REPLACE VIEW student_mastery_history_safe AS
SELECT
    history.mastery_history_id,
    history.user_id,
    history.knowledge_point_id,
    node.knowledge_point_name,
    history.previous_mastery_level,
    history.new_mastery_level,
    history.previous_mastery_score,
    history.new_mastery_score,
    history.previous_memory_status,
    history.new_memory_status,
    history.new_memory_stability_days,
    history.confidence,
    history.reason_codes,
    history.algorithm_name,
    history.algorithm_version,
    history.state_version,
    history.next_review_at,
    history.created_at
FROM learner_mastery_history AS history
JOIN knowledge_nodes AS node ON node.knowledge_point_id = history.knowledge_point_id
WHERE history.user_id = current_setting('app.current_user_id', TRUE);

-- Applies a precomputed deterministic update. The function owns idempotency,
-- evidence ownership, optimistic locking, history, and the current-state write.
CREATE OR REPLACE FUNCTION apply_mastery_update(
    p_user_id TEXT,
    p_knowledge_point_id TEXT,
    p_expected_state_version INTEGER,
    p_update_id TEXT,
    p_update JSONB
) RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    current_state learner_mastery_current%ROWTYPE;
    new_state_version INTEGER;
    evidence_id_value TEXT;
    evidence_count INTEGER;
    last_evidence TEXT;
BEGIN
    IF length(btrim(COALESCE(p_user_id, ''))) = 0
       OR length(btrim(COALESCE(p_knowledge_point_id, ''))) = 0
       OR length(btrim(COALESCE(p_update_id, ''))) = 0 THEN
        RAISE EXCEPTION 'userId, knowledgePointId, and updateId are required';
    END IF;
    IF p_expected_state_version < 0 THEN
        RAISE EXCEPTION 'expectedStateVersion must be non-negative';
    END IF;
    IF jsonb_typeof(p_update) <> 'object'
       OR jsonb_typeof(p_update -> 'evidenceIds') <> 'array'
       OR jsonb_array_length(p_update -> 'evidenceIds') = 0
       OR jsonb_typeof(p_update -> 'reasonCodes') <> 'array'
       OR jsonb_typeof(p_update -> 'evidenceSummary') <> 'object' THEN
        RAISE EXCEPTION 'Malformed mastery update payload';
    END IF;
    IF (p_update ->> 'masteryLevel') NOT IN ('未评测', '不会', '了解', '熟悉', '掌握')
       OR (p_update ->> 'memoryStatus') NOT IN ('未验证', '首次验证', '延迟复测通过', '稳定保持')
       OR (p_update ->> 'masteryScore')::numeric NOT BETWEEN 0 AND 1
       OR (p_update ->> 'confidence')::numeric NOT BETWEEN 0 AND 1
       OR COALESCE((p_update ->> 'memoryStabilityDays')::numeric, 0) < 0
       OR length(btrim(COALESCE(p_update ->> 'algorithmName', ''))) = 0
       OR length(btrim(COALESCE(p_update ->> 'algorithmVersion', ''))) = 0 THEN
        RAISE EXCEPTION 'Mastery update value is outside its contract';
    END IF;

    -- Idempotent retries return before checking the caller's now-stale expected
    -- version. Reusing the same ID for another learner/state is still rejected.
    IF EXISTS (
        SELECT 1 FROM learner_mastery_history
        WHERE mastery_history_id = p_update_id
          AND (user_id <> p_user_id OR knowledge_point_id <> p_knowledge_point_id)
    ) THEN
        RAISE EXCEPTION 'updateId has already been used for another state' USING ERRCODE = '23505';
    END IF;
    IF EXISTS (SELECT 1 FROM learner_mastery_history WHERE mastery_history_id = p_update_id) THEN
        SELECT state_version INTO new_state_version
        FROM learner_mastery_history WHERE mastery_history_id = p_update_id;
        RETURN new_state_version;
    END IF;

    SELECT * INTO current_state
    FROM learner_mastery_current
    WHERE user_id = p_user_id AND knowledge_point_id = p_knowledge_point_id
    FOR UPDATE;

    IF FOUND AND current_state.state_version <> p_expected_state_version THEN
        RAISE EXCEPTION 'Mastery state version conflict: expected %, actual %',
            p_expected_state_version, current_state.state_version USING ERRCODE = '40001';
    ELSIF NOT FOUND AND p_expected_state_version <> 0 THEN
        RAISE EXCEPTION 'Mastery state version conflict: expected %, actual 0',
            p_expected_state_version USING ERRCODE = '40001';
    END IF;

    SELECT count(*), max(value)
    INTO evidence_count, last_evidence
    FROM jsonb_array_elements_text(p_update -> 'evidenceIds');
    IF evidence_count <> (
        SELECT count(DISTINCT value) FROM jsonb_array_elements_text(p_update -> 'evidenceIds')
    ) THEN
        RAISE EXCEPTION 'evidenceIds contains duplicates';
    END IF;
    IF evidence_count <> (
        SELECT count(*)
        FROM assessment_evidence AS evidence
        WHERE evidence.evidence_id IN (
            SELECT value FROM jsonb_array_elements_text(p_update -> 'evidenceIds')
        )
          AND evidence.user_id = p_user_id
          AND evidence.knowledge_point_id = p_knowledge_point_id
          AND evidence.evidence_strength <> 'none'
          AND evidence.score IS NOT NULL
          AND evidence.task_mode IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Evidence is missing, non-effective, or belongs to another learner/knowledge point';
    END IF;
    IF EXISTS (
        SELECT 1 FROM mastery_evidence_processing AS processed
        WHERE processed.evidence_id IN (
            SELECT value FROM jsonb_array_elements_text(p_update -> 'evidenceIds')
        )
    ) THEN
        RAISE EXCEPTION 'One or more evidence events have already been processed' USING ERRCODE = '23505';
    END IF;

    new_state_version := COALESCE(current_state.state_version, 0) + 1;
    INSERT INTO learner_mastery_history (
        mastery_history_id, user_id, knowledge_point_id,
        previous_mastery_level, new_mastery_level,
        previous_mastery_score, new_mastery_score,
        previous_memory_status, new_memory_status,
        previous_memory_stability_days, new_memory_stability_days,
        confidence, evidence_ids, evidence_summary, reason_codes,
        algorithm_name, algorithm_version, state_version, next_review_at
    ) VALUES (
        p_update_id, p_user_id, p_knowledge_point_id,
        current_state.mastery_level, p_update ->> 'masteryLevel',
        current_state.mastery_score, (p_update ->> 'masteryScore')::numeric,
        current_state.memory_status, p_update ->> 'memoryStatus',
        current_state.memory_stability_days, (p_update ->> 'memoryStabilityDays')::numeric,
        (p_update ->> 'confidence')::numeric, p_update -> 'evidenceIds',
        p_update -> 'evidenceSummary', p_update -> 'reasonCodes',
        p_update ->> 'algorithmName', p_update ->> 'algorithmVersion',
        new_state_version, NULLIF(p_update ->> 'nextReviewAt', '')::timestamptz
    );

    FOR evidence_id_value IN
        SELECT value FROM jsonb_array_elements_text(p_update -> 'evidenceIds')
    LOOP
        INSERT INTO mastery_evidence_processing
            (evidence_id, mastery_history_id, algorithm_name, algorithm_version)
        VALUES
            (evidence_id_value, p_update_id,
             p_update ->> 'algorithmName', p_update ->> 'algorithmVersion');
    END LOOP;

    SELECT evidence_id INTO last_evidence
    FROM assessment_evidence
    WHERE evidence_id IN (
        SELECT value FROM jsonb_array_elements_text(p_update -> 'evidenceIds')
    )
    ORDER BY occurred_at DESC, evidence_id DESC
    LIMIT 1;

    INSERT INTO learner_mastery_current (
        user_id, knowledge_point_id, mastery_level, mastery_score,
        memory_status, memory_stability_days, confidence, evidence_summary,
        algorithm_name, algorithm_version, reason_codes, last_evidence_id,
        last_evidence_at, next_review_at, state_version, updated_at
    )
    SELECT
        p_user_id, p_knowledge_point_id, p_update ->> 'masteryLevel',
        (p_update ->> 'masteryScore')::numeric, p_update ->> 'memoryStatus',
        (p_update ->> 'memoryStabilityDays')::numeric,
        (p_update ->> 'confidence')::numeric, p_update -> 'evidenceSummary',
        p_update ->> 'algorithmName', p_update ->> 'algorithmVersion',
        p_update -> 'reasonCodes', last_evidence, max(evidence.occurred_at),
        NULLIF(p_update ->> 'nextReviewAt', '')::timestamptz,
        new_state_version, now()
    FROM assessment_evidence AS evidence
    WHERE evidence.evidence_id IN (
        SELECT value FROM jsonb_array_elements_text(p_update -> 'evidenceIds')
    )
    ON CONFLICT (user_id, knowledge_point_id) DO UPDATE SET
        mastery_level = EXCLUDED.mastery_level,
        mastery_score = EXCLUDED.mastery_score,
        memory_status = EXCLUDED.memory_status,
        memory_stability_days = EXCLUDED.memory_stability_days,
        confidence = EXCLUDED.confidence,
        evidence_summary = EXCLUDED.evidence_summary,
        algorithm_name = EXCLUDED.algorithm_name,
        algorithm_version = EXCLUDED.algorithm_version,
        reason_codes = EXCLUDED.reason_codes,
        last_evidence_id = EXCLUDED.last_evidence_id,
        last_evidence_at = EXCLUDED.last_evidence_at,
        next_review_at = EXCLUDED.next_review_at,
        state_version = EXCLUDED.state_version,
        updated_at = now();

    INSERT INTO ai_assessments (
        assessment_id, user_id, knowledge_point_id, level, confidence,
        evidence_ids, reason_codes, algorithm_version
    ) VALUES (
        'ai-' || p_update_id, p_user_id, p_knowledge_point_id,
        p_update ->> 'masteryLevel', (p_update ->> 'confidence')::numeric,
        p_update -> 'evidenceIds', p_update -> 'reasonCodes',
        p_update ->> 'algorithmVersion'
    );

    RETURN new_state_version;
END
$$;

-- Publishes human-approved prerequisite candidates atomically. Any cycle in
-- the resulting prerequisite graph aborts the complete batch.
CREATE OR REPLACE FUNCTION publish_knowledge_edge_batch(
    p_batch_id TEXT,
    p_batch_name TEXT,
    p_requested_by TEXT,
    p_manifest_hash TEXT,
    p_edges JSONB
) RETURNS INTEGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    edge_payload JSONB;
    published_count INTEGER := 0;
BEGIN
    IF length(btrim(COALESCE(p_batch_id, ''))) = 0
       OR length(btrim(COALESCE(p_batch_name, ''))) = 0
       OR length(btrim(COALESCE(p_requested_by, ''))) = 0
       OR length(btrim(COALESCE(p_manifest_hash, ''))) = 0
       OR jsonb_typeof(p_edges) <> 'array'
       OR jsonb_array_length(p_edges) = 0 THEN
        RAISE EXCEPTION 'Batch metadata and a non-empty edge array are required';
    END IF;
    IF jsonb_array_length(p_edges) <> (
        SELECT count(DISTINCT value ->> 'edgeCandidateId') FROM jsonb_array_elements(p_edges)
    ) THEN
        RAISE EXCEPTION 'Duplicate edgeCandidateId in publication payload';
    END IF;

    PERFORM pg_advisory_xact_lock(hashtext(p_batch_id));
    INSERT INTO knowledge_edge_publication_batches (
        edge_publication_batch_id, batch_name, requested_by, manifest_hash,
        status, validation_report, published_at
    ) VALUES (
        p_batch_id, p_batch_name, p_requested_by, p_manifest_hash,
        'published', jsonb_build_object('edgeCount', jsonb_array_length(p_edges)), now()
    );

    FOR edge_payload IN SELECT value FROM jsonb_array_elements(p_edges)
    LOOP
        IF length(btrim(COALESCE(edge_payload ->> 'reviewerId', ''))) = 0
           OR edge_payload ->> 'reviewStatus' <> 'approved' THEN
            RAISE EXCEPTION 'Every edge requires an explicit approved decision and reviewerId';
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM knowledge_edge_candidates AS candidate
            WHERE candidate.edge_candidate_id = edge_payload ->> 'edgeCandidateId'
              AND candidate.from_knowledge_point_id = edge_payload ->> 'fromKnowledgePointId'
              AND candidate.to_knowledge_point_id = edge_payload ->> 'toKnowledgePointId'
              AND candidate.relation_type = edge_payload ->> 'relationType'
              AND candidate.status IN ('pending', 'approved')
        ) THEN
            RAISE EXCEPTION 'Edge candidate validation failed: %', edge_payload ->> 'edgeCandidateId';
        END IF;

        UPDATE knowledge_edge_candidates
        SET status = 'approved', reviewed_by = edge_payload ->> 'reviewerId', reviewed_at = now()
        WHERE edge_candidate_id = edge_payload ->> 'edgeCandidateId';

        INSERT INTO knowledge_edges (
            from_knowledge_point_id, to_knowledge_point_id, relation_type, weight
        )
        SELECT from_knowledge_point_id, to_knowledge_point_id, relation_type, confidence
        FROM knowledge_edge_candidates
        WHERE edge_candidate_id = edge_payload ->> 'edgeCandidateId'
        ON CONFLICT (from_knowledge_point_id, to_knowledge_point_id, relation_type)
        DO UPDATE SET weight = EXCLUDED.weight;

        INSERT INTO knowledge_edge_review_records (
            edge_review_id, edge_candidate_id, reviewer_id, review_status,
            review_note, checked_direction, checked_cycle
        ) VALUES (
            'edge-review-' || md5(p_batch_id || chr(31) || (edge_payload ->> 'edgeCandidateId')),
            edge_payload ->> 'edgeCandidateId', edge_payload ->> 'reviewerId', 'approved',
            edge_payload ->> 'reviewerNote', TRUE, TRUE
        );

        INSERT INTO knowledge_edge_publication_batch_items (
            edge_publication_batch_id, edge_candidate_id,
            from_knowledge_point_id, to_knowledge_point_id,
            relation_type, reviewer_id
        ) VALUES (
            p_batch_id, edge_payload ->> 'edgeCandidateId',
            edge_payload ->> 'fromKnowledgePointId', edge_payload ->> 'toKnowledgePointId',
            edge_payload ->> 'relationType', edge_payload ->> 'reviewerId'
        );
        published_count := published_count + 1;
    END LOOP;

    IF EXISTS (
        WITH RECURSIVE walk(start_id, current_id, path, cycle) AS (
            SELECT edge.from_knowledge_point_id, edge.to_knowledge_point_id,
                   ARRAY[edge.from_knowledge_point_id, edge.to_knowledge_point_id],
                   edge.to_knowledge_point_id = edge.from_knowledge_point_id
            FROM knowledge_edges AS edge
            WHERE edge.relation_type = 'prerequisite'
            UNION ALL
            SELECT walk.start_id, edge.to_knowledge_point_id,
                   walk.path || edge.to_knowledge_point_id,
                   edge.to_knowledge_point_id = ANY(walk.path)
            FROM walk
            JOIN knowledge_edges AS edge
              ON edge.from_knowledge_point_id = walk.current_id
             AND edge.relation_type = 'prerequisite'
            WHERE NOT walk.cycle
        )
        SELECT 1 FROM walk WHERE cycle LIMIT 1
    ) THEN
        RAISE EXCEPTION 'Prerequisite publication would create a cycle';
    END IF;

    RETURN published_count;
END
$$;

REVOKE ALL ON FUNCTION apply_mastery_update(TEXT, TEXT, INTEGER, TEXT, JSONB) FROM PUBLIC;
REVOKE ALL ON FUNCTION publish_knowledge_edge_batch(TEXT, TEXT, TEXT, TEXT, JSONB) FROM PUBLIC;

COMMIT;
