#!/usr/bin/env python3
"""Audit imported Quiz quality without changing review or publication state."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", " ", value.lower()).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", required=True, type=Path)
    parser.add_argument("--quiz-mappings", required=True, type=Path)
    parser.add_argument("--practice-mappings", required=True, type=Path)
    parser.add_argument("--localizations", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    items = [json.loads(line) for line in args.items.read_text(encoding="utf-8").splitlines() if line.strip()]
    quizzes = [item for item in items if item["item_type"] == "quiz_question"]
    practice = [item for item in items if item["item_type"] != "quiz_question"]
    with args.quiz_mappings.open(encoding="utf-8", newline="") as stream:
        quiz_mappings = {row["learning_item_id"]: row for row in csv.DictReader(stream)}
    with args.practice_mappings.open(encoding="utf-8", newline="") as stream:
        practice_mappings = {row["learning_item_id"]: row for row in csv.DictReader(stream)}
    with args.localizations.open(encoding="utf-8", newline="") as stream:
        localizations = {row["learning_item_id"]: row for row in csv.DictReader(stream)}

    stems: dict[str, list[str]] = defaultdict(list)
    for item in quizzes:
        stems[normalized(item["stem"])].append(item["learning_item_id"])
    duplicate_ids = {
        item_id
        for ids in stems.values()
        if len(ids) > 1
        for item_id in ids
    }

    review_rows: list[dict[str, Any]] = []
    correct_positions: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    for item in quizzes:
        blockers: list[str] = []
        warnings: list[str] = []
        options = item.get("options") or []
        correct = [option for option in options if option.get("is_correct") is True]
        if item["source"]["source_id"] not in {
            "microsoft-ml-for-beginners", "microsoft-ai-for-beginners"
        }:
            blockers.append("INVALID_SOURCE")
        if len(correct) != 1:
            blockers.append("CORRECT_OPTION_COUNT")
        else:
            correct_positions[str(correct[0]["key"])] += 1
            if normalized(item.get("answer_data", {}).get("answer", "")) != normalized(correct[0]["text"]):
                blockers.append("ANSWER_OPTION_MISMATCH")
        if len(options) < 2:
            blockers.append("TOO_FEW_OPTIONS")
        option_texts = [normalized(option["text"]) for option in options]
        if len(option_texts) != len(set(option_texts)):
            blockers.append("DUPLICATE_OPTIONS")
        if item["learning_item_id"] in duplicate_ids:
            warnings.append("DUPLICATE_NORMALIZED_STEM")
        if len(normalized(item["stem"]).split()) < 4:
            warnings.append("VERY_SHORT_STEM")
        if re.search(r"\b(all|none|both) of the above\b", " ".join(option_texts)):
            warnings.append("COMPOUND_OPTION_REVIEW")
        if re.search(r"\b(not|never|except|least|incorrect)\b", item["stem"].lower()):
            warnings.append("NEGATIVE_WORDING_REVIEW")
        if item["learning_item_id"] not in quiz_mappings:
            blockers.append("MISSING_MAPPING_CANDIDATE")

        localization = localizations.get(item["learning_item_id"])
        if not localization:
            blockers.append("MISSING_ZH_LOCALIZATION")
        else:
            localized_fields = [localization["zh_stem"]] + [
                localization.get(f"zh_option_{key.lower()}", "")
                for key in [str(option["key"]) for option in options]
            ]
            if not all(value.strip() for value in localized_fields):
                blockers.append("INCOMPLETE_ZH_LOCALIZATION")
            if not re.search(r"[\u3400-\u9fff]", localization["zh_stem"]):
                blockers.append("ZH_STEM_HAS_NO_CHINESE")
            try:
                explanation = json.loads(localization["explanation_data_json"])
            except (json.JSONDecodeError, TypeError):
                blockers.append("INVALID_EXPLANATION_JSON")
            else:
                if explanation.get("quality") == "structural_draft":
                    warnings.append("STRUCTURAL_EXPLANATION_NEEDS_SME_REVIEW")
                if explanation.get("requiresSubjectMatterReview") is not True:
                    blockers.append("EXPLANATION_REVIEW_FLAG_MISSING")
            if localization["translation_review_status"] != "pending" or localization["publish_decision"] != "hold":
                warnings.append("REVIEW_STATE_CHANGED_RECHECK_RELEASE")

        for code in blockers:
            blocker_counts[code] += 1
        for code in warnings:
            warning_counts[code] += 1
        review_rows.append(
            {
                "learning_item_id": item["learning_item_id"],
                "source_id": item["source"]["source_id"],
                "source_item_key": item["source_item_key"],
                "question_stem": item["stem"],
                "correct_option_key": correct[0]["key"] if len(correct) == 1 else "",
                "blocker_codes": "|".join(sorted(set(blockers))),
                "warning_codes": "|".join(sorted(set(warnings))),
                "quality_status": "blocked" if blockers else ("needs_review" if warnings else "structurally_valid"),
                "reviewer_id": "",
                "reviewer_note": "",
            }
        )

    if set(practice_mappings) != {item["learning_item_id"] for item in practice}:
        blocker_counts["PRACTICE_MAPPING_COVERAGE"] += 1

    with (args.output_dir / "question_quality_review.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(review_rows[0]))
        writer.writeheader()
        writer.writerows(review_rows)

    report = {
        "valid": not blocker_counts,
        "scope": {
            "quiz_count": len(quizzes),
            "practice_count": len(practice),
            "allowed_sources": ["microsoft-ml-for-beginners", "microsoft-ai-for-beginners"],
        },
        "coverage": {
            "quiz_mapping_candidate_count": len(quiz_mappings),
            "practice_mapping_candidate_count": len(practice_mappings),
            "zh_localization_candidate_count": len(localizations),
        },
        "quiz_quality": {
            "structurally_valid_count": sum(row["quality_status"] == "structurally_valid" for row in review_rows),
            "needs_review_count": sum(row["quality_status"] == "needs_review" for row in review_rows),
            "blocked_count": sum(row["quality_status"] == "blocked" for row in review_rows),
            "correct_option_distribution": dict(sorted(correct_positions.items())),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "warning_counts": dict(sorted(warning_counts.items())),
        },
        "release_state": "hold",
        "note": "结构审计通过不等于内容审核通过；警告项仍需学科人员确认。",
    }
    (args.output_dir / "question_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report["quiz_quality"], ensure_ascii=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
