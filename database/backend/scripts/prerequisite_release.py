#!/usr/bin/env python3
"""Audit prerequisite candidates and emit an atomic publication call."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


ALLOWED_DECISIONS = {"pending", "approved", "changes_requested", "rejected"}


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def find_cycle(rows: list[dict[str, str]]) -> list[str] | None:
    graph: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row["relation_type"] == "prerequisite" and row["review_status"] == "approved":
            graph[row["from_knowledge_point_id"]].append(row["to_knowledge_point_id"])
    visiting: set[str] = set()
    visited: set[str] = set()
    path: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visiting:
            start = path.index(node)
            return path[start:] + [node]
        if node in visited:
            return None
        visiting.add(node)
        path.append(node)
        for target in graph[node]:
            cycle = visit(target)
            if cycle:
                return cycle
        path.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in list(graph):
        cycle = visit(node)
        if cycle:
            return cycle
    return None


def audit(rows: list[dict[str, str]], known_nodes: set[str]) -> dict[str, Any]:
    errors: list[str] = []
    ids = [row["edge_candidate_id"] for row in rows]
    if len(ids) != len(set(ids)):
        errors.append("duplicate_edge_candidate_id")
    for index, row in enumerate(rows, 2):
        decision = row.get("review_status", "")
        if decision not in ALLOWED_DECISIONS:
            errors.append(f"row_{index}:invalid_review_status")
        if row["from_knowledge_point_id"] == row["to_knowledge_point_id"]:
            errors.append(f"row_{index}:self_edge")
        if row["from_knowledge_point_id"] not in known_nodes or row["to_knowledge_point_id"] not in known_nodes:
            errors.append(f"row_{index}:unknown_knowledge_point")
        if decision == "approved" and not row.get("reviewer_id", "").strip():
            errors.append(f"row_{index}:approved_without_reviewer")
    cycle = find_cycle(rows)
    if cycle:
        errors.append("approved_prerequisite_cycle:" + "->".join(cycle))
    counts = {decision: sum(row.get("review_status") == decision for row in rows) for decision in sorted(ALLOWED_DECISIONS)}
    return {
        "valid": not errors,
        "candidate_count": len(rows),
        "decision_counts": counts,
        "approved_graph_acyclic": cycle is None,
        "ready_to_publish_count": counts["approved"] if not errors else 0,
        "errors": errors,
        "note": "只有人工标记 approved 且填写 reviewer_id 的边才会进入发布包。",
    }


def sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def release_sql(rows: list[dict[str, str]], batch_id: str, batch_name: str, actor: str) -> str:
    approved = [row for row in rows if row["review_status"] == "approved"]
    if not approved:
        raise ValueError("no approved prerequisite edges to publish")
    payload = [
        {
            "edgeCandidateId": row["edge_candidate_id"],
            "fromKnowledgePointId": row["from_knowledge_point_id"],
            "toKnowledgePointId": row["to_knowledge_point_id"],
            "relationType": row["relation_type"],
            "reviewStatus": "approved",
            "reviewerId": row["reviewer_id"],
            "reviewerNote": row.get("reviewer_note", ""),
        }
        for row in approved
    ]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    manifest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return (
        "-- Generated prerequisite publication; execute as app_content_publisher\n"
        "BEGIN;\n"
        "SELECT publish_knowledge_edge_batch(\n"
        f"  {sql_literal(batch_id)}, {sql_literal(batch_name)}, {sql_literal(actor)},\n"
        f"  {sql_literal(manifest)}, {sql_literal(canonical)}::jsonb\n"
        ");\n"
        "COMMIT;\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-csv", required=True, type=Path)
    parser.add_argument("--taxonomy", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--emit-sql", type=Path)
    parser.add_argument("--batch-id")
    parser.add_argument("--batch-name")
    parser.add_argument("--actor")
    args = parser.parse_args()
    rows = load_rows(args.review_csv)
    taxonomy = json.loads(args.taxonomy.read_text(encoding="utf-8"))
    report = audit(rows, {row["knowledge_point_id"] for row in taxonomy})
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.emit_sql:
        if not report["valid"]:
            raise SystemExit("cannot emit SQL: review file is invalid")
        if not all((args.batch_id, args.batch_name, args.actor)):
            raise SystemExit("--batch-id, --batch-name and --actor are required with --emit-sql")
        args.emit_sql.write_text(
            release_sql(rows, args.batch_id, args.batch_name, args.actor), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
