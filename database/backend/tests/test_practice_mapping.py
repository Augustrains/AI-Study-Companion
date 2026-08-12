import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GENERATED = ROOT / "backend/generated"


def test_practice_mapping_package():
    items = [
        json.loads(line)
        for line in (GENERATED / "curriculum_items.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    practice_ids = {item["learning_item_id"] for item in items if item["item_type"] != "quiz_question"}
    with (GENERATED / "practice_knowledge_mapping_candidates.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    report = json.loads((GENERATED / "practice_mapping_report.json").read_text(encoding="utf-8"))
    taxonomy = {
        row["knowledge_point_id"]
        for row in json.loads((GENERATED / "knowledge_taxonomy.json").read_text(encoding="utf-8"))
    }
    assert len(rows) == 122
    assert {row["learning_item_id"] for row in rows} == practice_ids
    assert all(row["review_status"] == "pending" for row in rows)
    assert all(row["knowledge_point_id"] in taxonomy for row in rows)
    assert report["valid"] is True
    assert report["mapping_candidate_count"] == 122
    seed = (GENERATED / "practice_mapping_seed.sql").read_text(encoding="utf-8")
    assert seed.count("INSERT INTO item_knowledge_map_candidates") == 122


if __name__ == "__main__":
    test_practice_mapping_package()
    print("practice mapping passed: 122 pending mappings")
