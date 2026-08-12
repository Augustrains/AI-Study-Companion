-- Adaptive Learning System - portable PostgreSQL schema
-- The schema keeps source content immutable, questions versioned, and
-- learner evidence append-only. JSONB is used only for extensible payloads.

BEGIN;

CREATE TABLE IF NOT EXISTS books (
    book_id TEXT PRIMARY KEY,
    book_name TEXT NOT NULL,
    topic_id TEXT,
    topic_name TEXT,
    source_note TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'planned', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS abilities (
    ability_id TEXT PRIMARY KEY,
    ability_name TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chapters (
    chapter_id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES books(book_id),
    chapter_name TEXT NOT NULL,
    parent_chapter_id TEXT REFERENCES chapters(chapter_id),
    source_path TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS knowledge_nodes (
    knowledge_point_id TEXT PRIMARY KEY,
    ability_id TEXT REFERENCES abilities(ability_id),
    chapter_id TEXT REFERENCES chapters(chapter_id),
    knowledge_point_name TEXT NOT NULL,
    description TEXT,
    node_level INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'draft', 'archived')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS knowledge_edges (
    from_knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    to_knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    relation_type TEXT NOT NULL CHECK (relation_type IN ('prerequisite', 'related', 'contains', 'extends')),
    weight NUMERIC(6, 4) NOT NULL DEFAULT 1.0,
    PRIMARY KEY (from_knowledge_point_id, to_knowledge_point_id, relation_type),
    CHECK (from_knowledge_point_id <> to_knowledge_point_id)
);

CREATE TABLE IF NOT EXISTS source_repositories (
    source_id TEXT PRIMARY KEY,
    repository_name TEXT NOT NULL,
    repository_url TEXT NOT NULL,
    commit_sha TEXT,
    license_name TEXT,
    imported_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS source_documents (
    source_document_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source_repositories(source_id),
    file_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    source_url TEXT,
    content_hash TEXT NOT NULL,
    raw_content TEXT,
    content_version TEXT,
    parse_status TEXT NOT NULL DEFAULT 'imported' CHECK (parse_status IN ('imported', 'parsed', 'failed', 'ignored')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source_id, file_path, content_hash)
);

CREATE TABLE IF NOT EXISTS learning_items (
    learning_item_id TEXT PRIMARY KEY,
    source_document_id TEXT REFERENCES source_documents(source_document_id),
    source_item_key TEXT NOT NULL,
    item_type TEXT NOT NULL CHECK (item_type IN (
        'quiz_question', 'concept_check', 'coding_task', 'notebook_lab',
        'project_task', 'retrieval_task', 'reflection_task'
    )),
    title TEXT,
    language TEXT NOT NULL DEFAULT 'en',
    current_version_id TEXT,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
        'imported', 'parsed', 'draft', 'needs_review', 'approved', 'published', 'deprecated', 'rejected'
    )),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source_document_id, source_item_key)
);

CREATE TABLE IF NOT EXISTS learning_item_versions (
    learning_item_version_id TEXT PRIMARY KEY,
    learning_item_id TEXT NOT NULL REFERENCES learning_items(learning_item_id),
    version_number INTEGER NOT NULL,
    stem TEXT NOT NULL,
    answer_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    explanation TEXT,
    estimated_minutes NUMERIC(8, 2),
    difficulty NUMERIC(5, 2),
    change_summary TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (learning_item_id, version_number)
);

ALTER TABLE learning_items
    DROP CONSTRAINT IF EXISTS learning_items_current_version_fk;
ALTER TABLE learning_items
    ADD CONSTRAINT learning_items_current_version_fk
    FOREIGN KEY (current_version_id) REFERENCES learning_item_versions(learning_item_version_id);

CREATE TABLE IF NOT EXISTS item_options (
    item_option_id TEXT PRIMARY KEY,
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    option_key TEXT NOT NULL,
    option_text TEXT NOT NULL,
    is_correct BOOLEAN,
    explanation TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE (learning_item_version_id, option_key)
);

CREATE TABLE IF NOT EXISTS item_knowledge_maps (
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    relation_type TEXT NOT NULL CHECK (relation_type IN ('target', 'prerequisite', 'application', 'misconception', 'related')),
    weight NUMERIC(6, 4) NOT NULL DEFAULT 1.0,
    mapping_confidence NUMERIC(5, 4),
    mapping_method TEXT NOT NULL DEFAULT 'manual',
    PRIMARY KEY (learning_item_version_id, knowledge_point_id, relation_type)
);

CREATE TABLE IF NOT EXISTS task_templates (
    task_template_id TEXT PRIMARY KEY,
    learning_item_id TEXT NOT NULL REFERENCES learning_items(learning_item_id),
    task_mode TEXT NOT NULL CHECK (task_mode IN ('diagnostic', 'guided_practice', 'independent', 'retrieval', 'remediation', 'challenge')),
    task_version_id TEXT REFERENCES learning_item_versions(learning_item_version_id),
    difficulty NUMERIC(5, 2),
    hint_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    feedback_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    retry_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    scaffold_level INTEGER NOT NULL DEFAULT 0,
    retrieval_interval_days NUMERIC(8, 2),
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'published', 'deprecated')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS question_review_records (
    review_id TEXT PRIMARY KEY,
    learning_item_version_id TEXT NOT NULL REFERENCES learning_item_versions(learning_item_version_id),
    reviewer_id TEXT,
    review_status TEXT NOT NULL CHECK (review_status IN ('pending', 'approved', 'changes_requested', 'rejected')),
    review_note TEXT,
    checked_answer BOOLEAN,
    checked_mapping BOOLEAN,
    checked_source BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS learner_goals (
    goal_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    book_id TEXT NOT NULL REFERENCES books(book_id),
    topic_id TEXT,
    target_level TEXT NOT NULL CHECK (target_level IN ('基本了解', '熟悉', '掌握')),
    weekly_hours NUMERIC(8, 2),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'paused', 'archived')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS diagnostic_attempts (
    diagnostic_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    goal_id TEXT REFERENCES learner_goals(goal_id),
    question_bank_version TEXT,
    status TEXT NOT NULL DEFAULT 'started' CHECK (status IN ('started', 'submitted', 'assessed', 'cancelled')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS assessment_evidence (
    evidence_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    diagnostic_id TEXT REFERENCES diagnostic_attempts(diagnostic_id),
    task_instance_id TEXT,
    learning_item_version_id TEXT REFERENCES learning_item_versions(learning_item_version_id),
    knowledge_point_id TEXT REFERENCES knowledge_nodes(knowledge_point_id),
    answer_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    score NUMERIC(8, 4),
    is_correct BOOLEAN,
    response_time_ms INTEGER,
    hint_count INTEGER NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    confidence_before NUMERIC(5, 4),
    confidence_after NUMERIC(5, 4),
    error_type TEXT,
    evidence_version TEXT,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ai_assessments (
    assessment_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    level TEXT NOT NULL CHECK (level IN ('不会', '了解', '熟悉', '掌握')),
    confidence NUMERIC(5, 4),
    evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    algorithm_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_calibrations (
    calibration_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    user_level TEXT NOT NULL CHECK (user_level IN ('不会', '了解', '熟悉', '掌握')),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS learning_plans (
    plan_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    goal_id TEXT REFERENCES learner_goals(goal_id),
    plan_version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'paused', 'completed', 'archived')),
    generated_by TEXT,
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS learning_tasks (
    task_id TEXT PRIMARY KEY,
    plan_id TEXT REFERENCES learning_plans(plan_id),
    task_template_id TEXT REFERENCES task_templates(task_template_id),
    user_id TEXT NOT NULL,
    knowledge_point_id TEXT REFERENCES knowledge_nodes(knowledge_point_id),
    task_type TEXT NOT NULL,
    priority NUMERIC(8, 4) NOT NULL DEFAULT 0,
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    estimated_minutes NUMERIC(8, 2),
    scheduled_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'assigned' CHECK (status IN ('assigned', 'started', 'completed', 'skipped', 'expired', 'abandoned')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE assessment_evidence
    DROP CONSTRAINT IF EXISTS assessment_evidence_task_instance_fk;
ALTER TABLE assessment_evidence
    ADD CONSTRAINT assessment_evidence_task_instance_fk
    FOREIGN KEY (task_instance_id) REFERENCES learning_tasks(task_id);

CREATE TABLE IF NOT EXISTS learning_events (
    event_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    goal_id TEXT REFERENCES learner_goals(goal_id),
    plan_id TEXT REFERENCES learning_plans(plan_id),
    task_id TEXT REFERENCES learning_tasks(task_id),
    learning_item_id TEXT REFERENCES learning_items(learning_item_id),
    knowledge_point_id TEXT REFERENCES knowledge_nodes(knowledge_point_id),
    context JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS learner_mastery_current (
    user_id TEXT NOT NULL,
    knowledge_point_id TEXT NOT NULL REFERENCES knowledge_nodes(knowledge_point_id),
    mastery_score NUMERIC(8, 4) NOT NULL DEFAULT 0,
    memory_stability_days NUMERIC(10, 4),
    confidence NUMERIC(5, 4),
    last_evidence_at TIMESTAMPTZ,
    next_review_at TIMESTAMPTZ,
    state_version INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, knowledge_point_id)
);

CREATE TABLE IF NOT EXISTS adaptive_decisions (
    decision_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    goal_id TEXT REFERENCES learner_goals(goal_id),
    knowledge_point_id TEXT REFERENCES knowledge_nodes(knowledge_point_id),
    decision_type TEXT NOT NULL,
    input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason_codes JSONB NOT NULL DEFAULT '[]'::jsonb,
    algorithm_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_source_documents_source ON source_documents(source_id);
CREATE INDEX IF NOT EXISTS idx_learning_items_status ON learning_items(status);
CREATE INDEX IF NOT EXISTS idx_item_versions_item ON learning_item_versions(learning_item_id, version_number DESC);
CREATE INDEX IF NOT EXISTS idx_item_maps_knowledge ON item_knowledge_maps(knowledge_point_id);
CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON learning_tasks(user_id, status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_evidence_user_knowledge ON assessment_evidence(user_id, knowledge_point_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_user_time ON learning_events(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_decisions_user_time ON adaptive_decisions(user_id, created_at DESC);

COMMIT;
