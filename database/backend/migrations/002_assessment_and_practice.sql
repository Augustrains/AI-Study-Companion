-- Split formal objective assessments from practice tasks.
-- Apply after 001_content_learning.sql and before curriculum_seed.sql.

BEGIN;

ALTER TABLE learning_items
    ADD COLUMN IF NOT EXISTS assessment_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS evaluation_mode TEXT NOT NULL DEFAULT 'manual_review'
        CHECK (evaluation_mode IN ('exact_answer', 'code_tests', 'notebook_tests', 'rubric', 'manual_review'));

CREATE TABLE IF NOT EXISTS evaluation_specs (
    evaluation_spec_id TEXT PRIMARY KEY,
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    evaluation_mode TEXT NOT NULL CHECK (evaluation_mode IN ('exact_answer', 'code_tests', 'notebook_tests', 'rubric', 'manual_review')),
    evidence_policy TEXT NOT NULL CHECK (evidence_policy IN ('direct', 'strong', 'auxiliary', 'none')),
    spec_version INTEGER NOT NULL,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'published', 'deprecated')),
    created_by TEXT,
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (learning_item_version_id, spec_version)
);

CREATE TABLE IF NOT EXISTS evaluation_test_cases (
    test_case_id TEXT PRIMARY KEY,
    evaluation_spec_id TEXT NOT NULL REFERENCES evaluation_specs(evaluation_spec_id),
    input_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    expected_output JSONB NOT NULL DEFAULT '{}'::jsonb,
    test_weight NUMERIC(8, 4) NOT NULL DEFAULT 1.0 CHECK (test_weight > 0),
    is_hidden BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evaluation_rubric_criteria (
    criterion_id TEXT PRIMARY KEY,
    evaluation_spec_id TEXT NOT NULL REFERENCES evaluation_specs(evaluation_spec_id),
    criterion_name TEXT NOT NULL,
    description TEXT NOT NULL,
    weight NUMERIC(8, 4) NOT NULL CHECK (weight > 0),
    score_levels JSONB NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS task_submissions (
    submission_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES learning_tasks(task_id),
    user_id TEXT NOT NULL,
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    submission_type TEXT NOT NULL CHECK (submission_type IN ('answer', 'code', 'notebook', 'artifact', 'link', 'text')),
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    artifact_url TEXT,
    submitted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evaluation_results (
    evaluation_result_id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES task_submissions(submission_id),
    evaluation_spec_id TEXT NOT NULL REFERENCES evaluation_specs(evaluation_spec_id),
    evaluator_name TEXT NOT NULL,
    evaluator_version TEXT NOT NULL,
    score NUMERIC(8, 4) CHECK (score IS NULL OR score BETWEEN 0 AND 1),
    is_passed BOOLEAN,
    confidence NUMERIC(5, 4) CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    feedback JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'needs_human_review')),
    evaluated_at TIMESTAMPTZ,
    UNIQUE (submission_id, evaluation_spec_id, evaluator_name, evaluator_version)
);

CREATE TABLE IF NOT EXISTS notebook_execution_runs (
    run_id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES task_submissions(submission_id),
    environment_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed', 'timed_out', 'blocked')),
    execution_log TEXT,
    artifact_url TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

ALTER TABLE assessment_evidence
    ADD COLUMN IF NOT EXISTS evaluation_result_id TEXT REFERENCES evaluation_results(evaluation_result_id),
    ADD COLUMN IF NOT EXISTS evidence_strength TEXT NOT NULL DEFAULT 'direct'
        CHECK (evidence_strength IN ('direct', 'strong', 'auxiliary', 'none'));

CREATE OR REPLACE VIEW published_quiz_bank AS
SELECT
    item.learning_item_id,
    item.current_version_id AS learning_item_version_id,
    item.title,
    item.language,
    item.evaluation_mode,
    document.source_id,
    document.source_url,
    version.stem,
    version.answer_data,
    version.explanation
FROM learning_items AS item
JOIN source_documents AS document ON document.source_document_id = item.source_document_id
JOIN learning_item_versions AS version ON version.learning_item_version_id = item.current_version_id
WHERE item.item_type = 'quiz_question'
  AND item.assessment_eligible = TRUE
  AND item.status = 'published'
  AND document.source_id IN ('microsoft-ml-for-beginners', 'microsoft-ai-for-beginners')
  AND version.answer_data ? 'answer'
  AND EXISTS (
      SELECT 1
      FROM evaluation_specs AS spec
      WHERE spec.learning_item_version_id = version.learning_item_version_id
        AND spec.evaluation_mode = 'exact_answer'
        AND spec.status = 'published'
  );

CREATE OR REPLACE VIEW student_practice_task_bank_safe AS
SELECT
    item.learning_item_id,
    item.current_version_id AS learning_item_version_id,
    item.item_type,
    item.title,
    item.language,
    item.evaluation_mode,
    document.source_id,
    document.source_url,
    version.stem
FROM learning_items AS item
JOIN source_documents AS document ON document.source_document_id = item.source_document_id
JOIN learning_item_versions AS version ON version.learning_item_version_id = item.current_version_id
WHERE item.assessment_eligible = FALSE
  AND item.item_type <> 'quiz_question'
  AND item.status = 'published'
  AND EXISTS (
      SELECT 1
      FROM evaluation_specs AS spec
      WHERE spec.learning_item_version_id = version.learning_item_version_id
        AND spec.status = 'published'
  )
  AND document.source_id IN ('microsoft-ml-for-beginners', 'microsoft-ai-for-beginners');

CREATE OR REPLACE VIEW practice_task_bank AS
SELECT * FROM student_practice_task_bank_safe;

CREATE OR REPLACE VIEW internal_practice_task_bank AS
SELECT
    item.learning_item_id,
    item.current_version_id AS learning_item_version_id,
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
JOIN source_documents AS document ON document.source_document_id = item.source_document_id
JOIN learning_item_versions AS version ON version.learning_item_version_id = item.current_version_id
JOIN evaluation_specs AS spec ON spec.learning_item_version_id = version.learning_item_version_id
WHERE item.assessment_eligible = FALSE
  AND item.item_type <> 'quiz_question'
  AND document.source_id IN ('microsoft-ml-for-beginners', 'microsoft-ai-for-beginners');

CREATE INDEX IF NOT EXISTS idx_learning_items_assessment ON learning_items(item_type, assessment_eligible, status);
CREATE INDEX IF NOT EXISTS idx_evaluation_specs_item ON evaluation_specs(learning_item_version_id, status);
CREATE INDEX IF NOT EXISTS idx_submissions_task ON task_submissions(task_id, submitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_evaluation_results_submission ON evaluation_results(submission_id, status);

COMMIT;
