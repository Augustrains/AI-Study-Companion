#!/usr/bin/env python3
"""Audit the Quiz review sheet and generate a guarded PostgreSQL release batch.

The script never approves content by itself. A reviewer must explicitly change
all three review columns to ``approved`` and ``publish_decision`` to ``publish``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List


ALLOWED_SOURCES = {
    "microsoft-ml-for-beginners",
    "microsoft-ai-for-beginners",
}
REVIEW_COLUMNS = (
    "mapping_review_status",
    "answer_review_status",
    "source_review_status",
)
VALID_REVIEW_STATUSES = {"pending", "approved", "changes_requested", "rejected"}


def stable_id(prefix: str, *parts: str) -> str:
    value = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(value).hexdigest()[:20]}"


def sql_text(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def sql_json(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sql_text(rendered) + "::jsonb"


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def audit(items_path: Path, review_path: Path) -> Dict[str, Any]:
    items = read_jsonl(items_path)
    quizzes = {item["learning_item_id"]: item for item in items if item["item_type"] == "quiz_question"}
    rows = read_csv(review_path)
    errors: List[str] = []

    if len(quizzes) != 301:
        errors.append(f"expected 301 Quiz items, got {len(quizzes)}")
    if len(rows) != 301:
        errors.append(f"expected 301 review rows, got {len(rows)}")
    row_ids = [row.get("learning_item_id", "") for row in rows]
    if len(row_ids) != len(set(row_ids)):
        errors.append("review sheet contains duplicate learning_item_id values")
    if set(row_ids) != set(quizzes):
        errors.append("review sheet Quiz IDs do not exactly match curriculum_items.jsonl")
    candidate_ids = [row.get("mapping_candidate_id", "") for row in rows]
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("review sheet contains duplicate mapping_candidate_id values")

    for number, row in enumerate(rows, start=2):
        item = quizzes.get(row.get("learning_item_id", ""))
        if not item:
            continue
        if row.get("source_id") not in ALLOWED_SOURCES:
            errors.append(f"row {number}: unapproved source_id")
        if row.get("source_id") != item["source"]["source_id"]:
            errors.append(f"row {number}: source_id differs from catalog")
        if row.get("source_file_path") != item["source"]["file_path"]:
            errors.append(f"row {number}: source_file_path differs from catalog")
        if row.get("source_item_key") != item["source_item_key"]:
            errors.append(f"row {number}: source_item_key differs from catalog")
        if row.get("source_commit") != item["source"].get("commit_sha"):
            errors.append(f"row {number}: source_commit differs from catalog")
        if row.get("source_content_hash") != item["source"].get("content_hash"):
            errors.append(f"row {number}: source_content_hash differs from catalog")
        if not row.get("knowledge_point_id"):
            errors.append(f"row {number}: missing knowledge_point_id")
        expected_version_id = stable_id("item-version", item["learning_item_id"], "1")
        if row.get("learning_item_version_id") != expected_version_id:
            errors.append(f"row {number}: learning_item_version_id differs from catalog")
        expected_candidate_id = stable_id(
            "mapping-candidate", expected_version_id, row.get("knowledge_point_id", ""), "target"
        )
        if row.get("mapping_candidate_id") != expected_candidate_id:
            errors.append(f"row {number}: mapping_candidate_id is inconsistent")
        try:
            confidence = float(row.get("mapping_confidence", ""))
            if not 0 <= confidence <= 1:
                raise ValueError
        except ValueError:
            errors.append(f"row {number}: mapping_confidence must be between 0 and 1")
        if row.get("question_stem") != item.get("stem"):
            errors.append(f"row {number}: question stem differs from catalog")
        if not (item.get("answer_data") or {}).get("answer"):
            errors.append(f"row {number}: source Quiz has no answer")
        correct_options = [option for option in item.get("options", []) if option.get("is_correct") is True]
        if len(correct_options) != 1:
            errors.append(f"row {number}: source Quiz does not have one correct option")
        else:
            if row.get("answer_text") != str(item["answer_data"]["answer"]):
                errors.append(f"row {number}: answer_text differs from catalog")
            if row.get("correct_option_key") != str(correct_options[0]["key"]):
                errors.append(f"row {number}: correct_option_key differs from catalog")
        for column in REVIEW_COLUMNS:
            if row.get(column) not in VALID_REVIEW_STATUSES:
                errors.append(f"row {number}: invalid {column}")
        decision = row.get("publish_decision")
        if decision not in {"hold", "publish", "reject"}:
            errors.append(f"row {number}: invalid publish_decision")
        if decision == "publish":
            if any(row.get(column) != "approved" for column in REVIEW_COLUMNS):
                errors.append(f"row {number}: publish requires all review statuses approved")
            if not row.get("reviewer_id", "").strip():
                errors.append(f"row {number}: publish requires reviewer_id")

    counts = {
        "mapping": dict(Counter(row.get("mapping_review_status", "missing") for row in rows)),
        "answer": dict(Counter(row.get("answer_review_status", "missing") for row in rows)),
        "source": dict(Counter(row.get("source_review_status", "missing") for row in rows)),
        "decision": dict(Counter(row.get("publish_decision", "missing") for row in rows)),
    }
    ready = [
        row for row in rows
        if row.get("publish_decision") == "publish"
        and all(row.get(column) == "approved" for column in REVIEW_COLUMNS)
        and row.get("reviewer_id", "").strip()
    ]
    return {
        "valid": not errors,
        "quiz_count": len(quizzes),
        "review_row_count": len(rows),
        "ready_to_publish_count": len(ready),
        "review_counts": counts,
        "errors": errors,
    }


def release_sql(
    rows: Iterable[Dict[str, str]],
    batch_id: str,
    batch_name: str,
    requested_by: str,
    source_commits: Dict[str, str],
) -> str:
    selected = list(rows)
    payload = [
        {
            "itemId": row["learning_item_id"],
            "versionId": row["learning_item_version_id"],
            "sourceId": row["source_id"],
            "sourceCommit": row["source_commit"],
            "sourceContentHash": row["source_content_hash"],
            "questionStem": row["question_stem"],
            "answerText": row["answer_text"],
            "correctOptionKey": row["correct_option_key"],
            "knowledgePointId": row["knowledge_point_id"],
            "candidateId": row["mapping_candidate_id"],
            "mappingConfidence": f"{float(row['mapping_confidence']):.4f}",
            "reviewerId": row["reviewer_id"].strip(),
            "reviewerNote": row.get("reviewer_note", "").strip(),
        }
        for row in selected
    ]
    manifest = {
        "sourceCommitSnapshot": source_commits,
        "items": payload,
    }
    manifest_hash = hashlib.sha256(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    lines = [
        "-- Human-approved Quiz release. Generated by review_release.py.",
        "-- A duplicate batch ID, duplicate manifest, changed source commit, or changed",
        "-- question/answer/correct option causes the entire transaction to roll back.",
        "BEGIN;",
        (
            "SELECT publish_quiz_batch("
            f"{sql_text(batch_id)}, {sql_text(batch_name)}, {sql_text(requested_by)}, "
            f"{sql_json(source_commits)}, {sql_text(manifest_hash)}, {sql_json(payload)});"
        ),
        "COMMIT;",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="validate and summarize a review sheet")
    audit_parser.add_argument("--items", type=Path, required=True)
    audit_parser.add_argument("--review", type=Path, required=True)
    audit_parser.add_argument("--report", type=Path)

    release_parser = subparsers.add_parser("build-release", help="generate SQL for explicitly approved rows")
    release_parser.add_argument("--items", type=Path, required=True)
    release_parser.add_argument("--review", type=Path, required=True)
    release_parser.add_argument("--output", type=Path, required=True)
    release_parser.add_argument("--batch-id", required=True)
    release_parser.add_argument("--batch-name", required=True)
    release_parser.add_argument("--requested-by", required=True)

    args = parser.parse_args()
    report = audit(args.items, args.review)
    if args.command == "audit":
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if report["valid"] else 1

    if not report["valid"]:
        raise SystemExit("review sheet failed audit; run the audit command for details")
    rows = read_csv(args.review)
    selected = [
        row for row in rows
        if row["publish_decision"] == "publish"
        and all(row[column] == "approved" for column in REVIEW_COLUMNS)
        and row["reviewer_id"].strip()
    ]
    if not selected:
        raise SystemExit("no rows are explicitly approved for publication")
    catalog = read_jsonl(args.items)
    source_commits = {
        item["source"]["source_id"]: item["source"]["commit_sha"]
        for item in catalog
        if item["source"]["source_id"] in ALLOWED_SOURCES
    }
    if set(source_commits) != ALLOWED_SOURCES:
        raise SystemExit("catalog does not contain both approved source commits")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        release_sql(selected, args.batch_id, args.batch_name, args.requested_by, source_commits),
        encoding="utf-8",
    )
    print(f"wrote release SQL for {len(selected)} Quiz items to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
