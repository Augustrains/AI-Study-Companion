#!/usr/bin/env python3
"""Extract a reviewable learning-item catalog from the two Microsoft curricula.

The importer is deliberately conservative: it keeps source provenance, emits
candidate knowledge labels, and marks imported items as ``needs_review``. It
does not invent answers or publish content automatically.

Example:
    python3 backend/scripts/import_curriculum.py \
      --repo ml=/tmp/ML-For-Beginners \
      --repo ai=/tmp/AI-For-Beginners \
      --output backend/generated/curriculum_items.jsonl \
      --report backend/generated/curriculum_report.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple


REPOSITORIES = {
    "ml": {
        "source_id": "microsoft-ml-for-beginners",
        "name": "ML-For-Beginners",
        "url": "https://github.com/microsoft/ML-For-Beginners",
    },
    "ai": {
        "source_id": "microsoft-ai-for-beginners",
        "name": "AI-For-Beginners",
        "url": "https://github.com/microsoft/AI-For-Beginners",
    },
}

SKIP_DIRS = {
    ".git",
    ".github",
    "node_modules",
    "dist",
    "build",
    "translations",
    "translated_images",
}
TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".json", ".ipynb", ".yml", ".yaml"}
MARKER_RE = re.compile(
    r"\b(quiz|question|knowledge check|challenge|assignment|exercise|lab|project|practice|review|test)\b|"
    r"测验|题目|知识检查|挑战|作业|练习|实验|项目|复习|测试",
    re.IGNORECASE,
)
QUESTION_KEYS = ("question", "questionText", "question_text", "prompt", "stem")
ANSWER_KEYS = ("answer", "answerKey", "answer_key", "correctAnswer", "correct_answer", "correct")
OPTION_KEYS = ("options", "choices", "answers", "answerOptions")

KNOWLEDGE_TERMS = {
    "logistic regression": "logistic-regression",
    "linear regression": "linear-regression",
    "regression": "regression",
    "classification": "classification",
    "clustering": "clustering",
    "natural language processing": "nlp",
    "\bnlp\b": "nlp",
    "time series": "time-series",
    "reinforcement learning": "reinforcement-learning",
    "q-learning": "q-learning",
    "neural network": "neural-networks",
    "deep learning": "deep-learning",
    "computer vision": "computer-vision",
    "convolutional neural network": "cnn",
    "\bcnn\b": "cnn",
    "transformer": "transformers",
    "\bbert\b": "bert",
    "large language model": "llm",
    "\bllm\b": "llm",
    "overfitting": "overfitting",
    "fairness": "fairness",
    "pytorch": "pytorch",
    "tensorflow": "tensorflow",
}


def stable_id(prefix: str, *parts: str) -> str:
    value = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(value).hexdigest()[:20]}"


def compact(text: str, limit: int = 6000) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def git_commit(repo_root: Path) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    value = result.stdout.strip()
    return value or None


def iter_source_files(repo_root: Path) -> Iterator[Path]:
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        relative = path.relative_to(repo_root).as_posix()
        parts = set(path.relative_to(repo_root).parts)
        english_quiz_file = (
            relative == "quiz-app/src/assets/translations/en.json"
            or re.fullmatch(r"etc/quiz-app/src/assets/translations/en/lesson-\d+\.json", relative) is not None
        )
        if any(part in SKIP_DIRS for part in parts if part != "translations") or ("translations" in parts and not english_quiz_file):
            continue
        yield path


def source_url(repo_url: str, commit: Optional[str], relative_path: str) -> str:
    ref = commit or "main"
    return f"{repo_url}/blob/{ref}/{relative_path}"


def infer_knowledge(text: str) -> List[str]:
    lowered = text.lower()
    found: List[str] = []
    for term, slug in KNOWLEDGE_TERMS.items():
        if re.search(term, lowered, re.IGNORECASE) and slug not in found:
            found.append(slug)
    return found


def infer_item_type(title: str, body: str, suffix: str) -> str:
    text = f"{title} {body}".lower()
    if suffix == ".ipynb" or "notebook" in text or "lab" in text:
        return "notebook_lab"
    if "coding" in text or "code" in text or "implement" in text or "编程" in text:
        return "coding_task"
    if "challenge" in text or "assignment" in text or "project" in text or "作业" in text:
        return "project_task"
    if "quiz" in text or "question" in text or "测验" in text or "题目" in text:
        return "quiz_question"
    if "review" in text or "recall" in text or "复习" in text or "回忆" in text:
        return "retrieval_task"
    return "concept_check"


def evaluation_profile(item_type: str) -> Dict[str, Any]:
    """Describe how an item may become valid learning evidence.

    The profile is a candidate configuration, not an approval. Human review must
    attach a versioned evaluation spec before a practice task affects mastery.
    """
    profiles = {
        "quiz_question": {
            "assessment_role": "formal_quiz",
            "assessment_eligible": True,
            "evaluation_mode": "exact_answer",
            "mastery_evidence_policy": "direct_after_review",
        },
        "coding_task": {
            "assessment_role": "practice_task",
            "assessment_eligible": False,
            "evaluation_mode": "code_tests",
            "mastery_evidence_policy": "strong_after_validated_tests",
        },
        "notebook_lab": {
            "assessment_role": "practice_task",
            "assessment_eligible": False,
            "evaluation_mode": "notebook_tests",
            "mastery_evidence_policy": "strong_after_validated_tests",
        },
        "project_task": {
            "assessment_role": "practice_task",
            "assessment_eligible": False,
            "evaluation_mode": "rubric",
            "mastery_evidence_policy": "auxiliary_after_review",
        },
    }
    return profiles.get(item_type, {
        "assessment_role": "practice_task",
        "assessment_eligible": False,
        "evaluation_mode": "manual_review",
        "mastery_evidence_policy": "none",
    })


def extract_rubric_candidates(text: str, title: str) -> List[Dict[str, Any]]:
    """Extract Markdown rubric rows as candidates that still require review."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"^#{1,6}\s+rubric\s*$", line.strip(), re.IGNORECASE):
            continue
        table_lines: List[str] = []
        for candidate in lines[index + 1:]:
            stripped = candidate.strip()
            if stripped.startswith("|") and stripped.endswith("|"):
                table_lines.append(stripped)
            elif table_lines and stripped:
                break
        if len(table_lines) < 3:
            continue
        headers = [compact(cell) for cell in table_lines[0].strip("|").split("|")]
        rows = table_lines[2:]
        rubric: List[Dict[str, Any]] = []
        for row_index, row in enumerate(rows, start=1):
            cells = [compact(cell, 1200) for cell in row.strip("|").split("|")]
            if not any(cells):
                continue
            while len(cells) < len(headers):
                cells.append("")
            criterion_name = cells[0] or (title if len(rows) == 1 else f"{title} {row_index}")
            levels = {
                headers[column] or f"level_{column}": cells[column]
                for column in range(1, min(len(headers), len(cells)))
                if cells[column]
            }
            if levels:
                rubric.append({
                    "criterion_name": criterion_name,
                    "description": f"Review criterion extracted from the source rubric for {title}.",
                    "weight": 1.0,
                    "score_levels": levels,
                    "sort_order": row_index - 1,
                })
        return rubric
    return []


def parse_options(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, dict):
        return [{"key": str(k), "text": compact(str(v))} for k, v in value.items()]
    if isinstance(value, list):
        result: List[Dict[str, Any]] = []
        for index, option in enumerate(value):
            if isinstance(option, dict):
                key = option.get("key", option.get("id", chr(65 + index)))
                text = option.get("text", option.get("answerText", option.get("label", option.get("value", option))))
                result.append({"key": str(key), "text": compact(str(text)), "is_correct": is_truthy(option.get("isCorrect")) if "isCorrect" in option else None})
            else:
                result.append({"key": chr(65 + index), "text": compact(str(option))})
        return result
    return []


def is_truthy(value: Any) -> bool:
    return value is True or (isinstance(value, str) and value.strip().lower() in {"true", "1", "yes", "correct"})


def json_question_from_dict(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    stem = next((data.get(key) for key in QUESTION_KEYS if data.get(key)), None)
    options_value = next((data.get(key) for key in OPTION_KEYS if data.get(key) is not None), None)
    if not stem or options_value is None:
        return None
    answer = next((data.get(key) for key in ANSWER_KEYS if data.get(key) is not None), None)
    if answer is None and isinstance(options_value, list):
        correct = [
            option.get("answerText", option.get("text", option.get("label", option.get("value"))))
            for option in options_value
            if isinstance(option, dict) and is_truthy(option.get("isCorrect"))
        ]
        answer = correct[0] if len(correct) == 1 else correct or None
    return {
        "title": compact(str(data.get("title", data.get("name", "")))) or None,
        "stem": compact(str(stem)),
        "options": parse_options(options_value),
        "answer": answer,
        "explanation": data.get("explanation") or data.get("rationale"),
    }


def walk_json_questions(value: Any) -> Iterator[Dict[str, Any]]:
    if isinstance(value, dict):
        item = json_question_from_dict(value)
        if item:
            yield item
        for child in value.values():
            yield from walk_json_questions(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json_questions(child)


def markdown_sections(text: str) -> Iterator[Tuple[str, str, int]]:
    matches = list(re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", text))
    if not matches:
        return
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        title = compact(match.group(2), 240)
        body = compact(text[start:end], 6000)
        yield title, body, index + 1


def markdown_items(text: str, relative_path: str, suffix: str) -> Iterator[Tuple[str, str, str, int]]:
    for title, body, anchor in markdown_sections(text):
        normalized_title = re.sub(r"\[[^\]]+\]\([^\)]+\)", "", title).strip().lower()
        title_is_question = title.rstrip().endswith(("?", "？"))
        title_is_task_marker = bool(re.fullmatch(
            r"(?:the )?(challenge|assignment|exercise|lab|project|practice|review|task|knowledge check|quiz)s?",
            normalized_title,
            re.IGNORECASE,
        ))
        title_is_quiz_link = "quiz" in normalized_title and not title_is_question
        if title_is_quiz_link:
            continue
        if normalized_title == "assignment" and "assignment.md" in body and len(body) < 400:
            # The lesson README only links to the real assignment document.
            continue
        if not title_is_question and not title_is_task_marker:
            continue
        if len(body) < 20 and not title_is_question:
            continue
        item_type = infer_item_type(title, body, suffix)
        stem = title if "?" in title or "？" in title else body
        yield title, stem, item_type, anchor


def document_title(text: str, fallback: str) -> str:
    match = re.search(r"(?m)^#{1,6}\s+(.+?)\s*$", text)
    return compact(match.group(1), 240) if match else fallback


def document_task(text: str, relative_path: str, item_type: str) -> Optional[Tuple[str, str, str]]:
    body = compact(text, 6000)
    if len(body) < 20:
        return None
    title = document_title(text, Path(relative_path).stem.replace("_", " ").replace("-", " "))
    return title, body, item_type


def notebook_text(payload: Dict[str, Any]) -> str:
    cells = payload.get("cells", [])
    chunks: List[str] = []
    for cell in cells:
        source = cell.get("source", [])
        if isinstance(source, list):
            source = "".join(source)
        if cell.get("cell_type") == "markdown":
            chunks.append(str(source))
    return "\n\n".join(chunks)


def notebook_task(payload: Dict[str, Any], relative_path: str) -> Optional[Tuple[str, str, str, str]]:
    text = notebook_text(payload)
    if text.strip():
        task = document_task(text, relative_path, "notebook_lab")
        if task:
            title, stem, item_type = task
            return title, stem, item_type, "notebook_document"
    code_cells = [
        cell for cell in payload.get("cells", [])
        if cell.get("cell_type") == "code" and "".join(cell.get("source", [])).strip()
    ]
    if code_cells:
        title = Path(relative_path).stem.replace("_", " ").replace("-", " ")
        stem = (
            f"Complete and explain the executable notebook at {relative_path}. "
            f"It contains {len(code_cells)} non-empty code cells."
        )
        return title, stem, "notebook_lab", "code_only_notebook"
    return None


def make_item(
    repo: Dict[str, str],
    repo_root: Path,
    commit: Optional[str],
    path: Path,
    source_key: str,
    title: Optional[str],
    stem: str,
    item_type: str,
    options: Optional[List[Dict[str, Any]]] = None,
    answer: Any = None,
    explanation: Optional[str] = None,
    anchor: Optional[str] = None,
    discovered_via: str = "markdown",
    metadata_extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    relative = path.relative_to(repo_root).as_posix()
    knowledge_text = f"{relative} {title or ''} {stem}"
    try:
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        content_hash = None
    source_item_key = source_key if anchor is None else f"{source_key}#section-{anchor}"
    item_id = stable_id("item", repo["source_id"], relative, source_item_key)
    profile = evaluation_profile(item_type)
    return {
        "learning_item_id": item_id,
        "source": {
            "source_id": repo["source_id"],
            "repository_name": repo["name"],
            "repository_url": repo["url"],
            "commit_sha": commit,
            "file_path": relative,
            "source_url": source_url(repo["url"], commit, relative),
            "content_hash": content_hash,
        },
        "source_item_key": source_item_key,
        "item_type": item_type,
        "title": title,
        "stem": compact(stem, 6000),
        "language": "en",
        "options": options or [],
        "answer_data": {"answer": answer} if answer is not None else {},
        "explanation": compact(str(explanation), 3000) if explanation else None,
        "knowledge_candidates": infer_knowledge(knowledge_text),
        "status": "needs_review",
        "metadata": {
            "discovered_via": discovered_via,
            "mapping_method": "term_candidate_only",
            "requires_answer_review": answer is None,
            "requires_knowledge_review": True,
            **profile,
            **(metadata_extra or {}),
        },
    }


def extract_repo(repo_key: str, repo_root: Path, commit_override: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    repo = REPOSITORIES[repo_key]
    commit = commit_override or git_commit(repo_root)
    items: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    file_count = 0
    files_with_items = set()

    for path in iter_source_files(repo_root):
        file_count += 1
        relative = path.relative_to(repo_root).as_posix()
        try:
            raw = path.read_text(encoding="utf-8", errors="ignore")
            item_count_before = len(items)
            if not raw.strip():
                continue
            if path.suffix.lower() == ".json":
                payload = json.loads(raw)
                for index, question in enumerate(walk_json_questions(payload)):
                    items.append(make_item(
                        repo, repo_root, commit, path, f"json-{index}",
                        question.get("title"), question["stem"], "quiz_question",
                        options=question.get("options"), answer=question.get("answer"),
                        explanation=question.get("explanation"), discovered_via="json",
                    ))
            elif path.suffix.lower() == ".ipynb":
                payload = json.loads(raw)
                task = notebook_task(payload, relative)
                if task:
                    title, stem, item_type, discovered_via = task
                    items.append(make_item(
                        repo, repo_root, commit, path, "notebook", title, stem,
                        item_type, discovered_via=discovered_via,
                    ))
            elif relative.endswith("assignment.md"):
                task = document_task(raw, relative, "project_task")
                if task:
                    title, stem, item_type = task
                    rubric_candidates = extract_rubric_candidates(raw, title)
                    items.append(make_item(
                        repo, repo_root, commit, path, "assignment", title, stem,
                        item_type, discovered_via="assignment_document",
                        metadata_extra={
                            "rubric_candidates": rubric_candidates,
                            "requires_rubric_review": True,
                        },
                    ))
            elif "/lab/" in relative and path.name.lower() == "readme.md":
                task = document_task(raw, relative, "notebook_lab")
                if task:
                    title, stem, item_type = task
                    items.append(make_item(
                        repo, repo_root, commit, path, "lab-readme", title, stem,
                        item_type, discovered_via="lab_readme",
                    ))
            else:
                for title, stem, item_type, anchor in markdown_items(raw, relative, path.suffix.lower()):
                    items.append(make_item(
                        repo, repo_root, commit, path, "markdown", title, stem,
                        item_type, anchor=anchor, discovered_via="markdown_section",
                    ))
            if len(items) > item_count_before:
                files_with_items.add(relative)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append({"file_path": relative, "error": str(exc)})

    report = {
        "source_id": repo["source_id"],
        "repository_name": repo["name"],
        "commit_sha": commit,
        "files_scanned": file_count,
        "files_with_items": len(files_with_items),
        "files_without_items": file_count - len(files_with_items),
        "items_extracted": len(items),
        "item_types": dict(Counter(item["item_type"] for item in items)),
        "knowledge_candidates": dict(Counter(
            candidate for item in items for candidate in item["knowledge_candidates"]
        )),
        "errors": errors,
    }
    return items, report


def parse_repo_arg(value: str) -> Tuple[str, Path]:
    key, separator, path = value.partition("=")
    if not separator or key not in REPOSITORIES:
        raise argparse.ArgumentTypeError("repo must be ml=/path/to/repo or ai=/path/to/repo")
    return key, Path(path).expanduser().resolve()


def parse_commit_arg(value: str) -> Tuple[str, str]:
    key, separator, commit = value.partition("=")
    if not separator or key not in REPOSITORIES or not commit:
        raise argparse.ArgumentTypeError("commit must be ml=SHA or ai=SHA")
    return key, commit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", type=parse_repo_arg, required=True, help="ml=PATH or ai=PATH")
    parser.add_argument("--commit", action="append", type=parse_commit_arg, default=[], help="optional pinned commit: ml=SHA or ai=SHA")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    repo_keys = [repo_key for repo_key, _ in args.repo]
    if sorted(repo_keys) != ["ai", "ml"]:
        raise SystemExit("Exactly one ml repository and one ai repository are required")

    all_items: List[Dict[str, Any]] = []
    repo_reports: List[Dict[str, Any]] = []
    seen_ids = set()
    commit_overrides = dict(args.commit)
    for repo_key, repo_root in args.repo:
        if not repo_root.exists():
            raise SystemExit(f"Repository path does not exist: {repo_root}")
        items, report = extract_repo(repo_key, repo_root, commit_overrides.get(repo_key))
        repo_reports.append(report)
        for item in items:
            if item["learning_item_id"] not in seen_ids:
                all_items.append(item)
                seen_ids.add(item["learning_item_id"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as stream:
        for item in all_items:
            stream.write(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n")

    report = {
        "schema_version": "learning-item-catalog.v1",
        "items_total": len(all_items),
        "status_counts": dict(Counter(item["status"] for item in all_items)),
        "item_type_counts": dict(Counter(item["item_type"] for item in all_items)),
        "formal_quiz_candidates": sum(
            1 for item in all_items
            if item["item_type"] == "quiz_question" and bool(item["answer_data"].get("answer"))
        ),
        "practice_task_candidates": sum(
            1 for item in all_items if item["item_type"] != "quiz_question"
        ),
        "repo_reports": repo_reports,
        "source_policy": "Only ML-For-Beginners and AI-For-Beginners are accepted.",
        "publish_policy": "Only reviewed/approved items may be published; imported items remain needs_review.",
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
