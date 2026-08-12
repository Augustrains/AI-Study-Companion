#!/usr/bin/env python3
"""Build pending knowledge-point mappings for all imported practice material."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ML_PATH_TO_KP = {
    "1-Introduction/1-intro-to-ML/": "kp-ml-intro",
    "1-Introduction/2-history-of-ML/": "kp-ml-history",
    "1-Introduction/3-fairness/": "kp-ml-fairness",
    "1-Introduction/4-techniques-of-ML/": "kp-ml-tools",
    "2-Regression/1-Tools/": "kp-ml-regression-intro",
    "2-Regression/2-Data/": "kp-ml-regression-data",
    "2-Regression/3-Linear/": "kp-ml-linear-polynomial-regression",
    "2-Regression/4-Logistic/": "kp-ml-logistic-regression",
    "3-Web-App/": "kp-ml-web-app",
    "4-Classification/1-Introduction/": "kp-ml-classification-intro",
    "4-Classification/2-Classifiers-1/": "kp-ml-classifiers-1",
    "4-Classification/3-Classifiers-2/": "kp-ml-classifiers-2",
    "4-Classification/4-Applied/": "kp-ml-classification-applied",
    "5-Clustering/1-Visualize/": "kp-ml-clustering-intro",
    "5-Clustering/2-K-Means/": "kp-ml-kmeans",
    "6-NLP/1-Introduction-to-NLP/": "kp-ml-nlp-intro",
    "6-NLP/2-Tasks/": "kp-ml-nlp-tasks",
    "6-NLP/3-Translation-Sentiment/": "kp-ml-nlp-translation",
    "6-NLP/4-Hotel-Reviews-1/": "kp-ml-nlp-sentiment-1",
    "6-NLP/5-Hotel-Reviews-2/": "kp-ml-nlp-sentiment-2",
    "7-TimeSeries/1-Introduction/": "kp-ml-timeseries-intro",
    "7-TimeSeries/2-ARIMA/": "kp-ml-timeseries-arima",
    "7-TimeSeries/3-SVR/": "kp-ml-timeseries-svr",
    "8-Reinforcement/1-QLearning/": "kp-ml-reinforcement-qlearning",
    "8-Reinforcement/2-Gym/": "kp-ml-reinforcement-gym",
    "9-Real-World/": "kp-ml-real-world-applications",
    "PyTorch_Fundamentals.ipynb": "kp-ml-tools",
}


def stable_id(prefix: str, *parts: str) -> str:
    value = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(value).hexdigest()[:20]}"


def item_version_id(item_id: str) -> str:
    return stable_id("item-version", item_id, "1")


def sql_text(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def infer_mapping(source_id: str, path: str) -> tuple[str, float, str]:
    if source_id == "microsoft-ml-for-beginners":
        matches = [(prefix, kp) for prefix, kp in ML_PATH_TO_KP.items() if path.startswith(prefix)]
        if len(matches) != 1:
            raise ValueError(f"Cannot uniquely map ML practice path: {path}")
        return matches[0][1], 0.95, f"课程目录 {matches[0][0]} 对应正式课程知识点"

    if path.startswith("examples/03-"):
        lesson = 3
    elif path.startswith("lessons/1-Intro/"):
        lesson = 1
    elif path.startswith("lessons/2-Symbolic/"):
        lesson = 2
    elif path.startswith("lessons/X-Extras/X1-MultiModal/"):
        # CLIP is mapped to transfer learning as a candidate; a reviewer may
        # redirect it to a future multimodal node without changing source data.
        lesson = 8
    else:
        match = re.search(r"/(\d{2})-[^/]+/", path)
        if not match:
            raise ValueError(f"Cannot derive AI lesson from practice path: {path}")
        lesson = int(match.group(1))
    if not 1 <= lesson <= 24:
        raise ValueError(f"AI lesson out of taxonomy range: {path}")
    confidence = 0.80 if "X-Extras" in path else 0.97
    return f"kp-ai-lesson-{lesson:02d}", confidence, f"课程文件路径归属于 AI 第 {lesson} 课"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--taxonomy", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    taxonomy = json.loads(args.taxonomy.read_text(encoding="utf-8"))
    names = {row["knowledge_point_id"]: row["knowledge_point_name"] for row in taxonomy}
    items = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    practice = [item for item in items if item["item_type"] != "quiz_question"]
    rows: list[dict[str, Any]] = []
    for item in practice:
        source = item["source"]
        kp_id, confidence, rationale = infer_mapping(source["source_id"], source["file_path"])
        if kp_id not in names:
            raise ValueError(f"Knowledge point is missing from taxonomy: {kp_id}")
        version_id = item_version_id(item["learning_item_id"])
        rows.append(
            {
                "mapping_candidate_id": stable_id("mapping-candidate", version_id, kp_id, "target"),
                "learning_item_id": item["learning_item_id"],
                "learning_item_version_id": version_id,
                "item_type": item["item_type"],
                "title": item.get("title") or "",
                "source_id": source["source_id"],
                "source_file_path": source["file_path"],
                "knowledge_point_id": kp_id,
                "knowledge_point_name": names[kp_id],
                "relation_type": "target",
                "confidence": f"{confidence:.2f}",
                "mapping_method": "curriculum_source_path_candidate",
                "rationale": rationale,
                "review_status": "pending",
                "reviewer_id": "",
                "reviewer_note": "",
            }
        )

    if len(rows) != 122 or len({row["learning_item_id"] for row in rows}) != 122:
        raise SystemExit(f"Expected 122 unique practice mappings, got {len(rows)}")
    csv_path = args.output_dir / "practice_knowledge_mapping_candidates.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    sql = ["-- Generated pending mappings for 122 practice materials", "BEGIN;"]
    for row in rows:
        sql.append(
            "INSERT INTO item_knowledge_map_candidates "
            "(mapping_candidate_id, learning_item_version_id, knowledge_point_id, relation_type, "
            "confidence, mapping_method, rationale, status) VALUES ("
            f"{sql_text(row['mapping_candidate_id'])}, {sql_text(row['learning_item_version_id'])}, "
            f"{sql_text(row['knowledge_point_id'])}, 'target', {row['confidence']}, "
            f"{sql_text(row['mapping_method'])}, {sql_text(row['rationale'])}, 'pending') "
            "ON CONFLICT (learning_item_version_id, knowledge_point_id, relation_type) DO NOTHING;"
        )
    sql.extend(["COMMIT;", ""])
    (args.output_dir / "practice_mapping_seed.sql").write_text("\n".join(sql), encoding="utf-8")

    report = {
        "valid": True,
        "practice_item_count": len(practice),
        "mapping_candidate_count": len(rows),
        "pending_count": sum(row["review_status"] == "pending" for row in rows),
        "source_counts": {
            source_id: sum(row["source_id"] == source_id for row in rows)
            for source_id in sorted({row["source_id"] for row in rows})
        },
        "item_type_counts": {
            item_type: sum(row["item_type"] == item_type for row in rows)
            for item_type in sorted({row["item_type"] for row in rows})
        },
        "low_confidence_candidates": sum(float(row["confidence"]) < 0.9 for row in rows),
        "note": "全部为待人工审核候选；未写入正式 item_knowledge_maps。",
    }
    (args.output_dir / "practice_mapping_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"generated {len(rows)} pending practice mappings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
