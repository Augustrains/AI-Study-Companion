#!/usr/bin/env python3
"""Build a complete, reviewable Quiz-to-course-knowledge mapping package."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


ML_TOPICS = [
    ("ml-intro", "Introduction to Machine Learning", "ml-foundations", "ML Foundations"),
    ("ml-history", "History of Machine Learning", "ml-foundations", "ML Foundations"),
    ("ml-fairness", "Fairness and Machine Learning", "ml-foundations", "ML Foundations"),
    ("ml-tools", "Tools and Techniques", "ml-foundations", "ML Foundations"),
    ("ml-regression-intro", "Introduction to Regression", "ml-regression", "Regression"),
    ("ml-regression-data", "Prepare and Visualize Data for Regression", "ml-regression", "Regression"),
    ("ml-linear-polynomial-regression", "Linear and Polynomial Regression", "ml-regression", "Regression"),
    ("ml-logistic-regression", "Logistic Regression", "ml-regression", "Regression"),
    ("ml-web-app", "Build a Web App", "ml-application", "ML Application"),
    ("ml-classification-intro", "Classification 1", "ml-classification", "Classification"),
    ("ml-classifiers-1", "Classification 2", "ml-classification", "Classification"),
    ("ml-classifiers-2", "Classification 3", "ml-classification", "Classification"),
    ("ml-classification-applied", "Classification 4", "ml-classification", "Classification"),
    ("ml-clustering-intro", "Introduction to Clustering", "ml-clustering", "Clustering"),
    ("ml-kmeans", "K-Means Clustering", "ml-clustering", "Clustering"),
    ("ml-nlp-intro", "Intro to NLP", "ml-nlp", "Natural Language Processing"),
    ("ml-nlp-tasks", "NLP Tasks", "ml-nlp", "Natural Language Processing"),
    ("ml-nlp-translation", "NLP and Translation", "ml-nlp", "Natural Language Processing"),
    ("ml-nlp-sentiment-1", "NLP 4", "ml-nlp", "Natural Language Processing"),
    ("ml-nlp-sentiment-2", "NLP 5", "ml-nlp", "Natural Language Processing"),
    ("ml-timeseries-intro", "Intro to Time Series", "ml-timeseries", "Time Series"),
    ("ml-timeseries-arima", "Time Series ARIMA", "ml-timeseries", "Time Series"),
    ("ml-reinforcement-qlearning", "Reinforcement 1", "ml-reinforcement", "Reinforcement Learning"),
    ("ml-reinforcement-gym", "Reinforcement 2", "ml-reinforcement", "Reinforcement Learning"),
    ("ml-real-world-applications", "Real World Applications", "ml-real-world", "Real-world ML"),
    ("ml-timeseries-svr", "Time Series SVR", "ml-timeseries", "Time Series"),
]

AI_TOPIC_NAMES = {
    1: "Introduction to AI", 2: "Knowledge Representation and Expert Systems",
    3: "Perceptron", 4: "Neural Networks", 5: "Deep Learning Frameworks",
    6: "Introduction to Computer Vision", 7: "Convolutional Neural Networks",
    8: "Pre-trained Networks and Transfer Learning", 9: "Autoencoders",
    10: "Generative Adversarial Networks", 11: "Object Detection", 12: "Segmentation",
    13: "Text Representation", 14: "Embeddings", 15: "Language Modeling",
    16: "Recurrent Neural Networks", 17: "Generative Networks", 18: "Transformers",
    19: "Named Entity Recognition", 20: "Large Language Models",
    21: "Genetic Algorithms", 22: "Reinforcement Learning",
    23: "Multi-Agent Modeling", 24: "Ethical and Responsible AI",
}


def ai_module(lesson: int) -> Tuple[str, str]:
    if lesson == 1:
        return "ai-foundations", "AI Foundations"
    if lesson == 2:
        return "ai-symbolic", "Symbolic AI"
    if 3 <= lesson <= 5:
        return "ai-neural", "Neural Networks"
    if 6 <= lesson <= 12:
        return "ai-vision", "Computer Vision"
    if 13 <= lesson <= 20:
        return "ai-nlp", "Natural Language Processing"
    if lesson == 21:
        return "ai-genetic", "Genetic Algorithms"
    if lesson in (22, 23):
        return "ai-agents", "Reinforcement and Multi-Agent Learning"
    return "ai-ethics", "Responsible AI"


def stable_id(prefix: str, *parts: str) -> str:
    value = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(value).hexdigest()[:20]}"


def sql_text(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def version_id(item_id: str) -> str:
    return stable_id("item-version", item_id, "1")


def mapping_for(item: Dict[str, Any]) -> Tuple[str, str, str, str, str, str, int, float]:
    source = item["source"]
    source_id = source["source_id"]
    source_key = item["source_item_key"]
    if source_id == "microsoft-ml-for-beginners":
        index = int(source_key.removeprefix("json-"))
        topic_index = index // 6
        node_slug, topic_name, module_slug, module_name = ML_TOPICS[topic_index]
        return (
            "book-microsoft-ml-for-beginners", "ML-For-Beginners",
            module_slug, module_name, node_slug, topic_name, topic_index + 1, 0.99,
        )
    match = re.search(r"lesson-(\d+)\.json$", source["file_path"])
    if not match:
        raise ValueError(f"Cannot derive AI lesson from {source['file_path']}")
    lesson = int(match.group(1))
    module_slug, module_name = ai_module(lesson)
    return (
        "book-microsoft-ai-for-beginners", "AI-For-Beginners",
        module_slug, module_name, f"ai-lesson-{lesson:02d}",
        AI_TOPIC_NAMES[lesson], lesson, 0.99,
    )


def read_items(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--overwrite-review",
        action="store_true",
        help="replace quiz_review.csv; omitted by default to preserve human review work",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    quizzes = [item for item in read_items(args.input) if item["item_type"] == "quiz_question"]
    rows: List[Dict[str, Any]] = []
    taxonomy: Dict[str, Dict[str, Any]] = {}
    for item in quizzes:
        book_id, book_name, module_slug, module_name, node_slug, topic_name, course_order, confidence = mapping_for(item)
        ability_id = f"ability-{module_slug}"
        chapter_id = f"chapter-{module_slug}"
        knowledge_point_id = f"kp-{node_slug}"
        taxonomy[knowledge_point_id] = {
            "book_id": book_id,
            "book_name": book_name,
            "ability_id": ability_id,
            "ability_name": module_name,
            "chapter_id": chapter_id,
            "chapter_name": module_name,
            "knowledge_point_id": knowledge_point_id,
            "knowledge_point_name": topic_name,
            "course_order": course_order,
        }
        item_version_id = version_id(item["learning_item_id"])
        candidate_id = stable_id("mapping-candidate", item_version_id, knowledge_point_id, "target")
        correct_options = [option for option in item["options"] if option.get("is_correct") is True]
        if len(correct_options) != 1:
            raise ValueError(f"Quiz {item['learning_item_id']} must have exactly one correct option")
        rows.append({
            "learning_item_id": item["learning_item_id"],
            "learning_item_version_id": item_version_id,
            "source_id": item["source"]["source_id"],
            "source_file_path": item["source"]["file_path"],
            "source_item_key": item["source_item_key"],
            "source_commit": item["source"]["commit_sha"],
            "source_content_hash": item["source"]["content_hash"],
            "question_stem": item["stem"],
            "answer_text": item["answer_data"]["answer"],
            "correct_option_key": str(correct_options[0]["key"]),
            "knowledge_point_id": knowledge_point_id,
            "knowledge_point_name": topic_name,
            "mapping_candidate_id": candidate_id,
            "mapping_confidence": f"{confidence:.2f}",
            "mapping_method": "upstream_quiz_group",
            "mapping_review_status": "pending",
            "answer_review_status": "pending",
            "source_review_status": "pending",
            "publish_decision": "hold",
            "reviewer_id": "",
            "reviewer_note": "",
        })

    if len(rows) != 301:
        raise SystemExit(f"Expected 301 Quiz mappings, got {len(rows)}")

    taxonomy_path = args.output_dir / "knowledge_taxonomy.json"
    taxonomy_path.write_text(
        json.dumps(list(sorted(taxonomy.values(), key=lambda row: row["knowledge_point_id"])), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    fieldnames = list(rows[0])
    candidates_path = args.output_dir / "quiz_knowledge_mapping_candidates.csv"
    with candidates_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    review_path = args.output_dir / "quiz_review.csv"
    if args.overwrite_review or not review_path.exists():
        with review_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    edge_rows: List[Dict[str, Any]] = []
    for book_id in sorted({row["book_id"] for row in taxonomy.values()}):
        course_nodes = sorted(
            (row for row in taxonomy.values() if row["book_id"] == book_id),
            key=lambda row: row["course_order"],
        )
        for previous, current in zip(course_nodes, course_nodes[1:]):
            edge_rows.append({
                "edge_candidate_id": stable_id(
                    "edge-candidate", previous["knowledge_point_id"], current["knowledge_point_id"], "prerequisite"
                ),
                "from_knowledge_point_id": previous["knowledge_point_id"],
                "from_knowledge_point_name": previous["knowledge_point_name"],
                "to_knowledge_point_id": current["knowledge_point_id"],
                "to_knowledge_point_name": current["knowledge_point_name"],
                "relation_type": "prerequisite",
                "confidence": "0.75",
                "mapping_method": "curriculum_sequence_candidate",
                "review_status": "pending",
                "reviewer_id": "",
                "reviewer_note": "",
            })
    edge_path = args.output_dir / "knowledge_edge_candidates.csv"
    with edge_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(edge_rows[0]))
        writer.writeheader()
        writer.writerows(edge_rows)

    sql: List[str] = ["-- Generated knowledge taxonomy and pending mapping candidates", "BEGIN;"]
    books = {
        row["book_id"]: row["book_name"] for row in taxonomy.values()
    }
    for book_id, book_name in sorted(books.items()):
        sql.append(
            "INSERT INTO books (book_id, book_name, source_note, status) VALUES ("
            f"{sql_text(book_id)}, {sql_text(book_name)}, 'Microsoft beginner curriculum', 'active') "
            "ON CONFLICT (book_id) DO UPDATE SET book_name=EXCLUDED.book_name;"
        )
    abilities = {
        row["ability_id"]: row["ability_name"] for row in taxonomy.values()
    }
    for ability_id, ability_name in sorted(abilities.items()):
        sql.append(
            "INSERT INTO abilities (ability_id, ability_name, description, status) VALUES ("
            f"{sql_text(ability_id)}, {sql_text(ability_name)}, 'Curriculum module used for reviewable Quiz mapping', 'active') "
            "ON CONFLICT (ability_id) DO UPDATE SET ability_name=EXCLUDED.ability_name;"
        )
    chapters = {
        row["chapter_id"]: row for row in taxonomy.values()
    }
    for chapter_id, row in sorted(chapters.items()):
        sql.append(
            "INSERT INTO chapters (chapter_id, book_id, chapter_name, source_path, sort_order) VALUES ("
            f"{sql_text(chapter_id)}, {sql_text(row['book_id'])}, {sql_text(row['chapter_name'])}, "
            f"{sql_text(row['chapter_id'])}, 0) ON CONFLICT (chapter_id) DO UPDATE SET chapter_name=EXCLUDED.chapter_name;"
        )
    for row in sorted(taxonomy.values(), key=lambda value: value["knowledge_point_id"]):
        sql.append(
            "INSERT INTO knowledge_nodes (knowledge_point_id, ability_id, chapter_id, knowledge_point_name, description, status, metadata) VALUES ("
            f"{sql_text(row['knowledge_point_id'])}, {sql_text(row['ability_id'])}, {sql_text(row['chapter_id'])}, "
            f"{sql_text(row['knowledge_point_name'])}, 'Course-native Quiz topic; requires product review before publication', "
            f"'draft', '{{\"mapping_status\":\"candidate\"}}'::jsonb) "
            "ON CONFLICT (knowledge_point_id) DO UPDATE SET knowledge_point_name=EXCLUDED.knowledge_point_name;"
        )
    for row in rows:
        sql.append(
            "INSERT INTO item_knowledge_map_candidates "
            "(mapping_candidate_id, learning_item_version_id, knowledge_point_id, relation_type, confidence, mapping_method, rationale, status) VALUES ("
            f"{sql_text(row['mapping_candidate_id'])}, {sql_text(row['learning_item_version_id'])}, "
            f"{sql_text(row['knowledge_point_id'])}, 'target', {row['mapping_confidence']}, "
            f"{sql_text(row['mapping_method'])}, 'Mapped from the upstream Quiz group or lesson file', 'pending') "
            "ON CONFLICT (learning_item_version_id, knowledge_point_id, relation_type) DO NOTHING;"
        )
    for row in edge_rows:
        sql.append(
            "INSERT INTO knowledge_edge_candidates "
            "(edge_candidate_id, from_knowledge_point_id, to_knowledge_point_id, relation_type, "
            "confidence, mapping_method, rationale, status) VALUES ("
            f"{sql_text(row['edge_candidate_id'])}, {sql_text(row['from_knowledge_point_id'])}, "
            f"{sql_text(row['to_knowledge_point_id'])}, 'prerequisite', {row['confidence']}, "
            "'curriculum_sequence_candidate', 'Adjacent topics in the upstream curriculum; requires pedagogical review', 'pending') "
            "ON CONFLICT (from_knowledge_point_id, to_knowledge_point_id, relation_type) DO NOTHING;"
        )
    sql.extend(["COMMIT;", ""])
    (args.output_dir / "knowledge_mapping_seed.sql").write_text("\n".join(sql), encoding="utf-8")
    print(
        f"wrote {len(rows)} Quiz mappings across {len(taxonomy)} knowledge points "
        f"with {len(edge_rows)} prerequisite candidates"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
