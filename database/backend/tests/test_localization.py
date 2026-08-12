#!/usr/bin/env python3
"""Verify zh-CN candidate completeness, review safety, and API isolation."""

import csv
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "backend" / "generated"


def main() -> int:
    items = [
        json.loads(line)
        for line in (GENERATED / "curriculum_items.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    quizzes = {item["learning_item_id"]: item for item in items if item["item_type"] == "quiz_question"}
    with (GENERATED / "quiz_localization_zh_review.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    report = json.loads((GENERATED / "localization_report.json").read_text(encoding="utf-8"))
    assert len(rows) == 301
    assert {row["learning_item_id"] for row in rows} == set(quizzes)
    assert report["translated_stem_count"] == 301
    assert report["translated_option_set_count"] == 301
    assert report["explanation_candidate_count"] == 301
    assert report["ready_to_publish_count"] == 0
    for row in rows:
        item = quizzes[row["learning_item_id"]]
        assert re.search(r"[\u3400-\u9fff]", row["zh_stem"])
        assert row["translation_review_status"] == "pending"
        assert row["explanation_review_status"] == "pending"
        assert row["publish_decision"] == "hold"
        assert row["reviewer_id"] == ""
        expected_keys = {str(option["key"]).lower() for option in item["options"]}
        for key in ("a", "b", "c"):
            assert bool(row[f"zh_option_{key}"]) == (key in expected_keys)
        explanation = json.loads(row["explanation_data_json"])
        assert explanation["correctOptionKey"] == row["correct_option_key"]
        assert explanation["requiresSubjectMatterReview"] is True
        assert explanation["quality"] == "structural_draft"
        assert explanation["sourceUrls"] == [item["source"]["source_url"]]
    # Known machine-translation failures are protected by the technical glossary.
    flattened = "\n".join(row["zh_stem"] + " " + row["zh_option_a"] + " " + row["zh_option_b"] + " " + row["zh_option_c"] for row in rows)
    assert "美国有线电视新闻网" not in flattened
    assert "克尼恩" not in flattened
    assert "数学图书馆" not in flattened

    migration = (ROOT / "backend" / "migrations" / "006_localization_and_explanations.sql").read_text(encoding="utf-8")
    pre_answer_view = migration.split("CREATE OR REPLACE VIEW student_quiz_localized_bank_safe AS", 1)[1].split("CREATE OR REPLACE FUNCTION get_student_quiz_feedback", 1)[0]
    pre_answer_sql = re.sub(r"--[^\n]*", "", pre_answer_view)
    assert "answer_data" not in pre_answer_sql
    assert "is_correct" not in pre_answer_sql
    assert "explanation_data" not in pre_answer_sql
    assert "result.status = 'completed'" in migration
    assert "submission.user_id = v_user_id" in migration

    sys.path.insert(0, str(ROOT / "backend" / "scripts"))
    from localization_release import audit, release_sql
    audit_report = audit(GENERATED / "curriculum_items.jsonl", GENERATED / "quiz_localization_zh_review.csv")
    assert audit_report["valid"] is True
    assert audit_report["ready_to_publish_count"] == 0
    approved = dict(rows[0])
    approved.update({
        "translation_review_status": "approved",
        "explanation_review_status": "approved",
        "publish_decision": "publish",
        "reviewer_id": "test-reviewer",
    })
    sql = release_sql([approved], quizzes, "localization-test", "Test zh-CN", "publisher-test")
    assert "SELECT publish_quiz_localization_batch" in sql
    assert "sourceContentHash" in sql
    assert "translationReviewStatus" in sql
    roles = (ROOT / "backend" / "migrations" / "007_localization_roles.sql").read_text(encoding="utf-8")
    publisher_section = roles.split("TO app_content_publisher;", 1)[1]
    assert "GRANT EXECUTE ON FUNCTION publish_quiz_localization_batch" in roles
    assert "GRANT INSERT, UPDATE" not in publisher_section
    print("localization passed: 301 zh-CN stems/options/explanations, all pending review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
