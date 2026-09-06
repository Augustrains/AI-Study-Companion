"""Create reviewable AI-for-Beginners course units from canonical lesson README files.

The output is deliberately marked pending review. It is not eligible for the
Qdrant index until a content reviewer changes both status fields to approved.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.material_qa.services import QdrantMaterialIndexer


DEFAULT_SOURCE = PROJECT_ROOT / "data/question_new/教材/AI-For-Beginners/lessons"
DEFAULT_OUTPUT = DEFAULT_SOURCE / "processed"
KNOWLEDGE_CATALOG = PROJECT_ROOT / "data/question_new/知识点/深度学习与AI知识点.json"
TAXONOMY = PROJECT_ROOT / "data/question_new/题目-教材映射/knowledge_taxonomy.json"


def lesson_number(path: Path, source_root: Path) -> int:
    """Map the repository path to its published AI-for-Beginners lesson number."""
    parts = path.relative_to(source_root).parts[:-1]
    # Ethical AI is stored under chapter 7 but is published as lesson 24.
    if parts == ("7-Ethics",):
        return 24
    for part in reversed(parts):
        match = re.fullmatch(r"(\d{1,2})-.+", part)
        if match:
            return int(match.group(1))
    raise ValueError(f"cannot determine lesson number: {path}")


def first_heading(text: str, fallback: str) -> str:
    match = re.search(r"^#[ \t]+(.+?)\s*$", text, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def source_commit(source_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(source_root.parent), "rev-parse", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def load_catalogues() -> tuple[dict[int, dict[str, str]], dict[int, dict[str, str]]]:
    knowledge_data = json.loads(KNOWLEDGE_CATALOG.read_text(encoding="utf-8"))
    knowledge = {
        int(item["knowledge_point_id"].rsplit("-", 1)[1]): item
        for item in knowledge_data["knowledge_points"]
    }
    taxonomy = {
        int(item["course_order"]): item
        for item in json.loads(TAXONOMY.read_text(encoding="utf-8"))
        if item.get("book_name") == "AI-For-Beginners"
    }
    return knowledge, taxonomy


def render_unit(*, source_path: Path, source_root: Path, commit: str, knowledge: dict[str, str], taxonomy: dict[str, str]) -> str:
    body = source_path.read_text(encoding="utf-8").strip()
    relative = source_path.relative_to(source_root).as_posix()
    title = first_heading(body, source_path.parent.name)
    knowledge_id = knowledge["knowledge_point_id"]
    return f"""---
content_unit_id: dl-unit-{lesson_number(source_path, source_root):03d}
book_id: dl-001
topic_id: {knowledge_id}
chapter: {taxonomy['chapter_name']}
knowledge_points: [{knowledge_id}]
source_id: src-microsoft-ai-for-beginners
source_relative_path: lessons/{relative}
source_commit: {commit}
license: MIT
source_url: https://github.com/microsoft/AI-For-Beginners/blob/{commit}/lessons/{relative}
attribution: Microsoft AI-For-Beginners
cleaning_status: pending_review
review_status: pending_review
reviewer:
reviewed_at:
review_method: source-selection-and-structure-template-v1
---

# {knowledge['name']}：{title}

## 学习目标

理解“{knowledge['name']}”的核心概念，并能结合原课程说明其用途和限制。

## 阅读重点

{knowledge['description']}

## 原文学习材料

{body}
"""


def build_units(*, source_root: Path, output_root: Path) -> list[Path]:
    knowledge, taxonomy = load_catalogues()
    commit = source_commit(source_root)
    candidates = [
        path
        for path in sorted(source_root.rglob("*.md"))
        if QdrantMaterialIndexer.is_course_article_candidate(
            book_id="dl", document_root=source_root, source_path=path
        )
    ]
    output_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for source_path in candidates:
        number = lesson_number(source_path, source_root)
        if number not in knowledge or number not in taxonomy:
            raise ValueError(f"lesson {number} has no knowledge-catalogue mapping: {source_path}")
        destination = output_root / f"dl-unit-{number:03d}.md"
        destination.write_text(
            render_unit(
                source_path=source_path,
                source_root=source_root,
                commit=commit,
                knowledge=knowledge[number],
                taxonomy=taxonomy[number],
            ),
            encoding="utf-8",
        )
        written.append(destination)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    written = build_units(source_root=args.source_dir.resolve(), output_root=args.output_dir.resolve())
    print(f"created_or_updated={len(written)}")
    print(f"output_dir={args.output_dir.resolve()}")
    print("status=pending_review; approve both status fields before rebuilding the dl index")


if __name__ == "__main__":
    main()
