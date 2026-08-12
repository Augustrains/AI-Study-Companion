import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "backend/generated"


def test_quality_audit_is_complete_and_non_publishing():
    report = json.loads((GENERATED / "question_quality_report.json").read_text(encoding="utf-8"))
    with (GENERATED / "question_quality_review.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert report["valid"] is True
    assert report["scope"]["quiz_count"] == 301
    assert report["scope"]["practice_count"] == 122
    assert report["coverage"]["quiz_mapping_candidate_count"] == 301
    assert report["coverage"]["practice_mapping_candidate_count"] == 122
    assert report["coverage"]["zh_localization_candidate_count"] == 301
    assert report["release_state"] == "hold"
    assert len(rows) == 301
    assert all(row["quality_status"] != "blocked" for row in rows)


if __name__ == "__main__":
    test_quality_audit_is_complete_and_non_publishing()
    print("question quality audit passed: 301 Quiz rows, zero structural blockers")
