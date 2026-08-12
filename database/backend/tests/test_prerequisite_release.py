import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "backend/generated"
sys.path.insert(0, str(ROOT / "backend/scripts"))

from prerequisite_release import audit, find_cycle, load_rows, release_sql  # noqa: E402


def test_current_candidates_are_valid_but_not_approved():
    rows = load_rows(GENERATED / "knowledge_edge_candidates.csv")
    taxonomy = json.loads((GENERATED / "knowledge_taxonomy.json").read_text(encoding="utf-8"))
    report = audit(rows, {row["knowledge_point_id"] for row in taxonomy})
    assert report["valid"] is True
    assert report["candidate_count"] == 48
    assert report["decision_counts"]["pending"] == 48
    assert report["ready_to_publish_count"] == 0


def test_cycle_is_rejected_and_release_calls_controlled_function():
    rows = [
        {
            "edge_candidate_id": "a",
            "from_knowledge_point_id": "kp-a",
            "to_knowledge_point_id": "kp-b",
            "relation_type": "prerequisite",
            "review_status": "approved",
            "reviewer_id": "reviewer",
            "reviewer_note": "",
        },
        {
            "edge_candidate_id": "b",
            "from_knowledge_point_id": "kp-b",
            "to_knowledge_point_id": "kp-a",
            "relation_type": "prerequisite",
            "review_status": "approved",
            "reviewer_id": "reviewer",
            "reviewer_note": "",
        },
    ]
    assert find_cycle(rows)
    rows.pop()
    sql = release_sql(rows, "edge-batch-test", "Test", "publisher")
    assert "SELECT publish_knowledge_edge_batch" in sql
    assert "INSERT INTO knowledge_edges" not in sql


if __name__ == "__main__":
    test_current_candidates_are_valid_but_not_approved()
    test_cycle_is_rejected_and_release_calls_controlled_function()
    print("prerequisite release passed: current graph pending, cycle detection active")
