#!/usr/bin/env python3
"""Verify answer isolation, taxonomy coverage, and review-release defaults."""

import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "backend" / "generated"
GOVERNANCE = ROOT / "backend" / "migrations" / "003_content_governance.sql"
HARDENING = ROOT / "backend" / "migrations" / "004_runtime_hardening.sql"
ROLES = ROOT / "backend" / "migrations" / "005_runtime_roles.sql"


def view_body(sql: str, start: str, end: str) -> str:
    return sql.split(start, 1)[1].split(end, 1)[0]


def main() -> int:
    items = [
        json.loads(line)
        for line in (GENERATED / "curriculum_items.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    quizzes = {item["learning_item_id"] for item in items if item["item_type"] == "quiz_question"}
    taxonomy = json.loads((GENERATED / "knowledge_taxonomy.json").read_text(encoding="utf-8"))
    with (GENERATED / "quiz_review.csv").open(encoding="utf-8", newline="") as stream:
        reviews = list(csv.DictReader(stream))
    report = json.loads((GENERATED / "publication_readiness_report.json").read_text(encoding="utf-8"))

    assert len(quizzes) == 301
    assert len(taxonomy) == 50
    assert len({row["knowledge_point_id"] for row in taxonomy}) == 50
    assert len(reviews) == 301
    assert {row["learning_item_id"] for row in reviews} == quizzes
    assert all(row["mapping_review_status"] == "pending" for row in reviews)
    assert all(row["answer_review_status"] == "pending" for row in reviews)
    assert all(row["source_review_status"] == "pending" for row in reviews)
    assert all(row["publish_decision"] == "hold" for row in reviews)
    assert report["valid"] is True
    assert report["ready_to_publish_count"] == 0

    governance = GOVERNANCE.read_text(encoding="utf-8")
    hardening = HARDENING.read_text(encoding="utf-8")
    student_view = view_body(governance, "CREATE OR REPLACE VIEW student_quiz_bank_safe AS", "CREATE VIEW published_quiz_bank")
    scoring_view = view_body(hardening, "CREATE VIEW internal_quiz_scoring_bank AS", "-- Only this SECURITY DEFINER")
    practice_view = view_body(hardening, "CREATE VIEW student_practice_task_bank_safe AS", "CREATE VIEW practice_task_bank")
    assert "answer_data" not in student_view
    assert "is_correct" not in student_view
    assert "answer_data" in scoring_view
    assert "isCorrect" in scoring_view
    assert "correct_option_key" in scoring_view
    assert "answer_data" not in practice_view
    assert "item.status = 'published'" in practice_view

    roles = ROLES.read_text(encoding="utf-8")
    assert "GRANT SELECT ON student_quiz_bank_safe" in roles
    assert "internal_quiz_scoring_bank" in roles
    assert "app_student_api" in roles
    assert "app_content_publisher" in roles
    assert "GRANT EXECUTE ON FUNCTION publish_quiz_batch" in roles
    assert "ENABLE ROW LEVEL SECURITY" in roles
    assert "current_setting('app.current_user_id', TRUE)" in roles
    reviewer_grants = roles.split("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_content_reviewer;", 1)[1].split(
        "REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_content_publisher;", 1
    )[0]
    assert "learning_items, task_templates" not in reviewer_grants

    sys.path.insert(0, str(ROOT / "backend" / "scripts"))
    from review_release import release_sql

    approved = dict(reviews[0])
    approved.update({
        "mapping_review_status": "approved",
        "answer_review_status": "approved",
        "source_review_status": "approved",
        "publish_decision": "publish",
        "reviewer_id": "test-reviewer",
    })
    source_commits = {
        item["source"]["source_id"]: item["source"]["commit_sha"]
        for item in items
    }
    generated_release = release_sql(
        [approved], "publication-test", "Test", "publisher-test", source_commits
    )
    assert "SELECT publish_quiz_batch" in generated_release
    assert "sourceContentHash" in generated_release
    assert "correctOptionKey" in generated_release
    assert "ON CONFLICT" not in generated_release
    print("content governance passed: 301 review rows, 50 knowledge points, answers isolated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
