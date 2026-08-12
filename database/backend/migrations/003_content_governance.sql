-- Content governance, answer isolation, knowledge mapping review, and release batches.
-- Apply after 002_assessment_and_practice.sql and before generated governance seeds.

BEGIN;

CREATE TABLE IF NOT EXISTS item_knowledge_map_candidates (
    mapping_candidate_id TEXT PRIMARY KEY,
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    relation_type TEXT NOT NULL DEFAULT 'target'
        CHECK (relation_type IN ('target', 'prerequisite', 'application', 'misconception', 'related')),
    confidence NUMERIC(5, 4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    mapping_method TEXT NOT NULL,
    rationale TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'superseded')),
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (learning_item_version_id, knowledge_point_id, relation_type)
);

CREATE TABLE IF NOT EXISTS content_review_batches (
    review_batch_id TEXT PRIMARY KEY,
    batch_name TEXT NOT NULL,
    source_commit_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'in_review', 'completed', 'cancelled')),
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS content_review_batch_items (
    review_batch_id TEXT NOT NULL REFERENCES content_review_batches(review_batch_id),
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    review_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'approved', 'changes_requested', 'rejected')),
    reviewer_id TEXT,
    review_note TEXT,
    reviewed_at TIMESTAMPTZ,
    PRIMARY KEY (review_batch_id, learning_item_version_id)
);

CREATE TABLE IF NOT EXISTS publication_batches (
    publication_batch_id TEXT PRIMARY KEY,
    batch_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'validated', 'published', 'failed', 'cancelled')),
    requested_by TEXT NOT NULL,
    validated_by TEXT,
    published_by TEXT,
    validation_report JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    validated_at TIMESTAMPTZ,
    published_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS publication_batch_items (
    publication_batch_id TEXT NOT NULL REFERENCES publication_batches(publication_batch_id),
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    evaluation_spec_id TEXT NOT NULL REFERENCES evaluation_specs(evaluation_spec_id),
    publish_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (publish_status IN ('pending', 'ready', 'published', 'blocked', 'failed')),
    blocker_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    published_at TIMESTAMPTZ,
    PRIMARY KEY (publication_batch_id, learning_item_version_id)
);

-- Internal reviewer view. It intentionally contains answers and must never be
-- granted to the student-facing API role.
CREATE OR REPLACE VIEW content_review_queue AS
SELECT
    item.learning_item_id,
    version.learning_item_version_id,
    item.item_type,
    item.status AS item_status,
    item.evaluation_mode,
    document.source_id,
    document.source_url,
    document.content_version AS source_commit,
    version.stem,
    version.answer_data,
    version.explanation,
    EXISTS (
        SELECT 1 FROM item_options AS option
        WHERE option.learning_item_version_id = version.learning_item_version_id
          AND option.is_correct = TRUE
    ) AS has_correct_option,
    (SELECT count(*) FROM item_knowledge_maps AS mapping
     WHERE mapping.learning_item_version_id = version.learning_item_version_id) AS approved_mapping_count,
    (SELECT count(*) FROM item_knowledge_map_candidates AS candidate
     WHERE candidate.learning_item_version_id = version.learning_item_version_id
       AND candidate.status = 'pending') AS pending_mapping_count,
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
          AND spec.status = 'published'
    ) AS evaluation_published
FROM learning_items AS item
JOIN learning_item_versions AS version
  ON version.learning_item_version_id = item.current_version_id
JOIN source_documents AS document
  ON document.source_document_id = item.source_document_id;

CREATE OR REPLACE VIEW publication_readiness AS
SELECT
    queue.*,
    CASE
        WHEN queue.source_id NOT IN ('microsoft-ml-for-beginners', 'microsoft-ai-for-beginners')
            THEN 'BLOCKED_SOURCE'
        WHEN queue.item_type = 'quiz_question' AND NOT queue.has_correct_option
            THEN 'BLOCKED_ANSWER'
        WHEN queue.approved_mapping_count = 0
            THEN 'BLOCKED_MAPPING'
        WHEN NOT queue.content_review_approved
            THEN 'BLOCKED_REVIEW'
        WHEN NOT queue.evaluation_published
            THEN 'BLOCKED_EVALUATION'
        ELSE 'READY'
    END AS readiness_status
FROM content_review_queue AS queue;

-- Replace the old answer-bearing view with a student-safe published view.
DROP VIEW IF EXISTS published_quiz_bank;

CREATE OR REPLACE VIEW student_quiz_bank_safe AS
SELECT
    item.learning_item_id,
    version.learning_item_version_id,
    item.title,
    item.language,
    document.source_id,
    document.source_url,
    version.stem,
    COALESCE((
        SELECT jsonb_agg(
            jsonb_build_object(
                'key', option.option_key,
                'text', option.option_text,
                'sortOrder', option.sort_order
            ) ORDER BY option.sort_order
        )
        FROM item_options AS option
        WHERE option.learning_item_version_id = version.learning_item_version_id
    ), '[]'::jsonb) AS options,
    COALESCE((
        SELECT jsonb_agg(mapping.knowledge_point_id ORDER BY mapping.knowledge_point_id)
        FROM item_knowledge_maps AS mapping
        WHERE mapping.learning_item_version_id = version.learning_item_version_id
          AND mapping.relation_type = 'target'
    ), '[]'::jsonb) AS knowledge_point_ids
FROM learning_items AS item
JOIN learning_item_versions AS version
  ON version.learning_item_version_id = item.current_version_id
JOIN source_documents AS document
  ON document.source_document_id = item.source_document_id
WHERE item.item_type = 'quiz_question'
  AND item.assessment_eligible = TRUE
  AND item.status = 'published'
  AND document.source_id IN ('microsoft-ml-for-beginners', 'microsoft-ai-for-beginners')
  AND EXISTS (
      SELECT 1 FROM evaluation_specs AS spec
      WHERE spec.learning_item_version_id = version.learning_item_version_id
        AND spec.evaluation_mode = 'exact_answer'
        AND spec.status = 'published'
  )
  AND EXISTS (
      SELECT 1 FROM item_knowledge_maps AS mapping
      WHERE mapping.learning_item_version_id = version.learning_item_version_id
        AND mapping.relation_type = 'target'
  );

CREATE VIEW published_quiz_bank AS
SELECT * FROM student_quiz_bank_safe;

-- Trusted scoring service only. This view contains answers and correct-option
-- flags. Do not expose it through student or browser credentials.
CREATE OR REPLACE VIEW internal_quiz_scoring_bank AS
SELECT
    item.learning_item_id,
    version.learning_item_version_id,
    spec.evaluation_spec_id,
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
JOIN evaluation_specs AS spec
  ON spec.learning_item_version_id = version.learning_item_version_id
 AND spec.evaluation_mode = 'exact_answer'
 AND spec.status = 'published'
WHERE item.item_type = 'quiz_question'
  AND item.status = 'published';

CREATE INDEX IF NOT EXISTS idx_map_candidates_status
    ON item_knowledge_map_candidates(status, knowledge_point_id);
CREATE INDEX IF NOT EXISTS idx_review_batch_items_status
    ON content_review_batch_items(review_batch_id, review_status);
CREATE INDEX IF NOT EXISTS idx_publication_batch_items_status
    ON publication_batch_items(publication_batch_id, publish_status);

COMMIT;
