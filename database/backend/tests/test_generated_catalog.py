#!/usr/bin/env python3
"""Audit the generated catalog against the approved two-repository policy."""

import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ITEMS = ROOT / "backend" / "generated" / "curriculum_items.jsonl"
SEED = ROOT / "backend" / "generated" / "curriculum_seed.sql"
MAPPING_SEED = ROOT / "backend" / "generated" / "knowledge_mapping_seed.sql"
EDGE_CANDIDATES = ROOT / "backend" / "generated" / "knowledge_edge_candidates.csv"
ALLOWED_SOURCES = {
    "microsoft-ml-for-beginners",
    "microsoft-ai-for-beginners",
}


def main() -> int:
    items = [
        json.loads(line)
        for line in ITEMS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    source_counts = Counter(item["source"]["source_id"] for item in items)
    type_counts = Counter(item["item_type"] for item in items)
    quizzes = [item for item in items if item["item_type"] == "quiz_question"]
    practice = [item for item in items if item["item_type"] != "quiz_question"]

    assert len(items) == 423
    assert set(source_counts) == ALLOWED_SOURCES
    assert source_counts["microsoft-ml-for-beginners"] == 203
    assert source_counts["microsoft-ai-for-beginners"] == 220
    assert len(quizzes) == 301
    assert len(practice) == 122
    assert type_counts == Counter({
        "quiz_question": 301,
        "notebook_lab": 82,
        "project_task": 35,
        "concept_check": 3,
        "coding_task": 2,
    })
    for quiz in quizzes:
        assert quiz["answer_data"].get("answer") not in (None, "")
        assert quiz["options"]
        assert sum(option.get("is_correct") is True for option in quiz["options"]) == 1
        correct = next(option for option in quiz["options"] if option.get("is_correct") is True)
        normalize = lambda value: re.sub(r"\s+", " ", str(value)).strip().casefold()
        assert normalize(quiz["answer_data"]["answer"]) == normalize(correct["text"])
        assert quiz["metadata"]["evaluation_mode"] == "exact_answer"
        assert quiz["metadata"]["assessment_eligible"] is True
    assert all(item["metadata"]["assessment_eligible"] is False for item in practice)

    seed = SEED.read_text(encoding="utf-8")
    mapping_seed = MAPPING_SEED.read_text(encoding="utf-8")
    assert seed.count("INSERT INTO source_repositories") == 2
    assert seed.count("'MIT'") >= 2
    assert seed.count("INSERT INTO learning_items") == 423
    assert seed.count("INSERT INTO evaluation_specs") == 423
    assert "microsoft-ml-for-beginners" in seed
    assert "microsoft-ai-for-beginners" in seed
    assert '"comparison_field":"internal_quiz_scoring_bank.correct_option_key"' in seed
    assert mapping_seed.count("INSERT INTO books") == 2
    assert mapping_seed.count("INSERT INTO knowledge_nodes") == 50
    assert mapping_seed.count("INSERT INTO item_knowledge_map_candidates") == 301
    assert mapping_seed.count("INSERT INTO knowledge_edge_candidates") == 48
    assert len(EDGE_CANDIDATES.read_text(encoding="utf-8").splitlines()) == 49

    print(
        "generated catalog passed: "
        f"{len(quizzes)} quizzes, {len(practice)} practice items, "
        f"sources={dict(source_counts)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
