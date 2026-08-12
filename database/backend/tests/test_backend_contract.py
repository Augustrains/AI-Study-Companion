#!/usr/bin/env python3
"""Static contract checks that do not require a running PostgreSQL server."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = [
    ROOT / "backend" / "migrations" / "001_content_learning.sql",
    ROOT / "backend" / "migrations" / "002_assessment_and_practice.sql",
    ROOT / "backend" / "migrations" / "003_content_governance.sql",
    ROOT / "backend" / "migrations" / "004_runtime_hardening.sql",
    ROOT / "backend" / "migrations" / "006_localization_and_explanations.sql",
    ROOT / "backend" / "migrations" / "008_algorithm_and_mastery.sql",
]
REPORT = ROOT / "backend" / "generated" / "curriculum_report.json"


def main() -> int:
    schema = "\n".join(path.read_text(encoding="utf-8") for path in SCHEMAS)
    required_tables = {
        "books",
        "abilities",
        "knowledge_nodes",
        "knowledge_edges",
        "source_repositories",
        "source_documents",
        "learning_items",
        "learning_item_versions",
        "item_options",
        "item_knowledge_maps",
        "task_templates",
        "question_review_records",
        "learner_goals",
        "diagnostic_attempts",
        "assessment_evidence",
        "ai_assessments",
        "user_calibrations",
        "learning_plans",
        "learning_tasks",
        "learning_events",
        "learner_mastery_current",
        "adaptive_decisions",
        "evaluation_specs",
        "evaluation_test_cases",
        "evaluation_rubric_criteria",
        "task_submissions",
        "evaluation_results",
        "notebook_execution_runs",
        "item_knowledge_map_candidates",
        "content_review_batches",
        "content_review_batch_items",
        "publication_batches",
        "publication_batch_items",
        "assessment_assignments",
        "api_idempotency_records",
        "knowledge_edge_candidates",
        "learning_item_enrichment_candidates",
        "learning_item_localizations",
        "item_quality_statistics",
        "item_option_localizations",
        "localization_review_records",
        "localization_publication_batches",
        "localization_publication_batch_items",
        "learner_mastery_history",
        "mastery_evidence_processing",
        "knowledge_edge_review_records",
        "knowledge_edge_publication_batches",
        "knowledge_edge_publication_batch_items",
    }
    for table in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in schema, table
    assert "current_version_id" in schema
    assert "CREATE VIEW published_quiz_bank" in schema
    assert "CREATE OR REPLACE VIEW practice_task_bank" in schema
    assert "CREATE VIEW student_practice_task_bank_safe" in schema
    assert "CREATE VIEW internal_practice_task_bank" in schema
    assert "CREATE OR REPLACE VIEW student_quiz_bank_safe" in schema
    assert "CREATE OR REPLACE VIEW internal_quiz_scoring_bank" in schema
    assert "CREATE OR REPLACE VIEW publication_readiness" in schema
    assert "CREATE OR REPLACE FUNCTION publish_quiz_batch" in schema
    assert "CREATE OR REPLACE VIEW student_quiz_localized_bank_safe" in schema
    assert "CREATE OR REPLACE FUNCTION get_student_quiz_feedback" in schema
    assert "CREATE OR REPLACE FUNCTION publish_quiz_localization_batch" in schema
    assert "CREATE OR REPLACE VIEW algorithm_knowledge_catalog" in schema
    assert "CREATE OR REPLACE VIEW algorithm_question_catalog" in schema
    assert "CREATE OR REPLACE VIEW algorithm_prerequisite_graph" in schema
    assert "CREATE OR REPLACE VIEW algorithm_evidence_feed" in schema
    assert "CREATE OR REPLACE VIEW algorithm_learner_state" in schema
    assert "CREATE OR REPLACE FUNCTION apply_mastery_update" in schema
    assert "CREATE OR REPLACE FUNCTION publish_knowledge_edge_batch" in schema
    assert REPORT.exists(), "run the curriculum importer before this check"
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["items_total"] == 423
    assert report["formal_quiz_candidates"] == 301
    assert report["practice_task_candidates"] == 122
    assert report["item_type_counts"]["quiz_question"] == 301
    assert {entry["source_id"] for entry in report["repo_reports"]} == {
        "microsoft-ml-for-beginners", "microsoft-ai-for-beginners"
    }
    print(f"backend contract passed: {len(required_tables)} tables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
