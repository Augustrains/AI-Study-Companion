#!/usr/bin/env python3
"""Static checks for answer isolation and controlled mastery writes."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = (ROOT / "backend/migrations/008_algorithm_and_mastery.sql").read_text(encoding="utf-8")
ROLES = (ROOT / "backend/migrations/009_algorithm_roles.sql").read_text(encoding="utf-8")


def view_body(name: str, next_marker: str) -> str:
    return MIGRATION.split(f"CREATE OR REPLACE VIEW {name} AS", 1)[1].split(next_marker, 1)[0]


def test_algorithm_views_exclude_answers_and_payloads():
    question = view_body("algorithm_question_catalog", "CREATE OR REPLACE VIEW algorithm_prerequisite_graph")
    evidence = view_body("algorithm_evidence_feed", "CREATE OR REPLACE VIEW algorithm_learner_state")
    for forbidden in ("answer_data", "is_correct", "evaluation_config", "expected_output"):
        assert forbidden not in question
    assert "submission.payload" not in evidence
    assert "evidence.answer_data" not in evidence


def test_algorithm_role_has_no_direct_table_write_or_answer_grant():
    algorithm_section = ROLES.split("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_learning_algorithm;", 1)[1].split(
        "GRANT SELECT ON student_knowledge_status_safe", 1
    )[0]
    assert "internal_quiz_scoring_bank" not in algorithm_section
    assert "item_options" not in algorithm_section
    assert "learning_item_versions" not in algorithm_section
    assert "GRANT EXECUTE ON FUNCTION apply_mastery_update" in algorithm_section
    assert not re.search(r"GRANT\s+(INSERT|UPDATE|DELETE)", algorithm_section)


def test_mastery_contract_has_history_idempotency_and_optimistic_locking():
    assert "mastery_evidence_processing" in MIGRATION
    assert "p_expected_state_version" in MIGRATION
    assert "FOR UPDATE" in MIGRATION
    assert "state version conflict" in MIGRATION
    assert "evidence events have already been processed" in MIGRATION


if __name__ == "__main__":
    test_algorithm_views_exclude_answers_and_payloads()
    test_algorithm_role_has_no_direct_table_write_or_answer_grant()
    test_mastery_contract_has_history_idempotency_and_optimistic_locking()
    print("algorithm security passed: safe views and controlled mastery writes")
