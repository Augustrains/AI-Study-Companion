#!/usr/bin/env python3
"""Audit zh-CN Quiz review rows and build an atomic reviewed release SQL."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


VALID_REVIEW = {"pending", "approved", "changes_requested", "rejected"}


def stable_id(prefix: str, *parts: str) -> str:
    raw = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:20]}"


def sql_text(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def sql_json(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sql_text(rendered) + "::jsonb"


def read_items(path: Path) -> Dict[str, Dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["learning_item_id"]: row for row in rows if row["item_type"] == "quiz_question"}


def read_review(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def audit(items_path: Path, review_path: Path) -> Dict[str, Any]:
    items = read_items(items_path)
    rows = read_review(review_path)
    errors: List[str] = []
    if len(items) != 301:
        errors.append(f"expected 301 Quiz items, got {len(items)}")
    if len(rows) != 301:
        errors.append(f"expected 301 localization rows, got {len(rows)}")
    ids = [row.get("learning_item_id", "") for row in rows]
    if len(ids) != len(set(ids)):
        errors.append("duplicate learning_item_id in localization review")
    if set(ids) != set(items):
        errors.append("localization review IDs do not match Quiz catalog")

    for number, row in enumerate(rows, start=2):
        item = items.get(row.get("learning_item_id", ""))
        if not item:
            continue
        expected_version = stable_id("item-version", item["learning_item_id"], "1")
        immutable = {
            "learning_item_version_id": expected_version,
            "source_id": item["source"]["source_id"],
            "source_file_path": item["source"]["file_path"],
            "source_item_key": item["source_item_key"],
            "source_commit": item["source"]["commit_sha"],
            "source_content_hash": item["source"]["content_hash"],
            "question_stem_en": item["stem"],
        }
        for column, expected in immutable.items():
            if row.get(column) != expected:
                errors.append(f"row {number}: {column} differs from source catalog")
        expected_options = {str(option["key"]).lower(): str(option["text"]) for option in item["options"]}
        correct = next(option for option in item["options"] if option.get("is_correct") is True)
        if row.get("correct_option_key") != str(correct["key"]):
            errors.append(f"row {number}: correct_option_key differs from source catalog")
        for key in ("a", "b", "c"):
            if row.get(f"option_{key}_en", "") != expected_options.get(key, ""):
                errors.append(f"row {number}: option_{key}_en differs from source catalog")
            translated = row.get(f"zh_option_{key}", "").strip()
            if key in expected_options and not translated:
                errors.append(f"row {number}: missing zh_option_{key}")
            if key not in expected_options and translated:
                errors.append(f"row {number}: unexpected zh_option_{key}")
        if not re.search(r"[\u3400-\u9fff]", row.get("zh_stem", "")):
            errors.append(f"row {number}: zh_stem has no Chinese text")
        try:
            explanation = json.loads(row.get("explanation_data_json", ""))
            if explanation.get("correctOptionKey") != str(correct["key"]):
                errors.append(f"row {number}: explanation correct option mismatch")
            if explanation.get("requiresSubjectMatterReview") is not True:
                errors.append(f"row {number}: explanation must require subject-matter review")
            if not explanation.get("sourceUrls"):
                errors.append(f"row {number}: explanation has no source URL")
        except (ValueError, TypeError):
            errors.append(f"row {number}: invalid explanation_data_json")
        for column in ("translation_review_status", "explanation_review_status"):
            if row.get(column) not in VALID_REVIEW:
                errors.append(f"row {number}: invalid {column}")
        decision = row.get("publish_decision")
        if decision not in {"hold", "publish", "reject"}:
            errors.append(f"row {number}: invalid publish_decision")
        if decision == "publish":
            if row.get("translation_review_status") != "approved" or row.get("explanation_review_status") != "approved":
                errors.append(f"row {number}: publish requires translation and explanation approval")
            if not row.get("reviewer_id", "").strip():
                errors.append(f"row {number}: publish requires reviewer_id")

    ready = [
        row for row in rows
        if row.get("publish_decision") == "publish"
        and row.get("translation_review_status") == "approved"
        and row.get("explanation_review_status") == "approved"
        and row.get("reviewer_id", "").strip()
    ]
    return {
        "valid": not errors,
        "quiz_count": len(items),
        "review_row_count": len(rows),
        "ready_to_publish_count": len(ready),
        "translation_review_counts": dict(Counter(row.get("translation_review_status", "missing") for row in rows)),
        "explanation_review_counts": dict(Counter(row.get("explanation_review_status", "missing") for row in rows)),
        "decision_counts": dict(Counter(row.get("publish_decision", "missing") for row in rows)),
        "errors": errors,
    }


def release_sql(rows: List[Dict[str, str]], items: Dict[str, Dict[str, Any]], batch_id: str, batch_name: str, requested_by: str) -> str:
    manifest_payload = [{
        "versionId": row["learning_item_version_id"],
        "locale": "zh-CN",
        "sourceCommit": row["source_commit"],
        "sourceContentHash": row["source_content_hash"],
        "stem": row["zh_stem"],
        "options": {key.upper(): row[f"zh_option_{key}"] for key in ("a", "b", "c") if row[f"zh_option_{key}"]},
        "explanation": json.loads(row["explanation_data_json"]),
        "translationMethod": row["translation_method"],
        "translationVersion": row["translation_version"],
        "translationReviewStatus": row["translation_review_status"],
        "explanationReviewStatus": row["explanation_review_status"],
        "reviewerId": row["reviewer_id"].strip(),
        "reviewerNote": row.get("reviewer_note", "").strip(),
    } for row in rows]
    manifest_hash = hashlib.sha256(
        json.dumps(manifest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return "\n".join([
        "-- Human-approved zh-CN Quiz localization release.",
        "-- Only the guarded SECURITY DEFINER publisher can mutate localization state.",
        "BEGIN;",
        "SELECT publish_quiz_localization_batch("
        f"{sql_text(batch_id)}, {sql_text(batch_name)}, {sql_text(requested_by)}, "
        f"{sql_text(manifest_hash)}, {sql_json(manifest_payload)});",
        "COMMIT;",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    audit_parser = sub.add_parser("audit")
    audit_parser.add_argument("--items", type=Path, required=True)
    audit_parser.add_argument("--review", type=Path, required=True)
    audit_parser.add_argument("--report", type=Path)
    release_parser = sub.add_parser("build-release")
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
            args.report.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if report["valid"] else 1
    if not report["valid"]:
        raise SystemExit("localization review failed audit")
    rows = [row for row in read_review(args.review) if row["publish_decision"] == "publish" and row["translation_review_status"] == "approved" and row["explanation_review_status"] == "approved" and row["reviewer_id"].strip()]
    if not rows:
        raise SystemExit("no localization rows are explicitly approved for publication")
    items = read_items(args.items)
    args.output.write_text(release_sql(rows, items, args.batch_id, args.batch_name, args.requested_by), encoding="utf-8")
    print(f"wrote localization release SQL for {len(rows)} Quiz items to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
