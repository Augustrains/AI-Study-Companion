#!/usr/bin/env python3
"""Generate reviewable zh-CN Quiz translations and structural explanations.

The English catalog remains immutable. Machine output is always written as
``needs_review`` and never published by this script.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import time
import urllib.parse
import urllib.request
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List


LOCALE = "zh-CN"
PROVIDER = "public_machine_translation"
PROVIDER_VERSION = "en-zh-candidate-2026-08-12"
SEPARATOR = "ZXQSEP9"

EXACT_TRANSLATIONS = {
    "true": "正确",
    "false": "错误",
    "all of the above": "以上全部",
    "a and b": "A 和 B",
    "none of the above": "以上都不是",
    "cnn": "CNN（卷积神经网络）",
    "rnn": "RNN（循环神经网络）",
    "knn": "KNN（K近邻）",
    "gan": "GAN（生成对抗网络）",
    "vae": "VAE（变分自动编码器）",
    "arima": "ARIMA",
    "svr": "SVR",
    "sgd": "SGD（随机梯度下降）",
    "tensorflow": "TensorFlow",
    "pytorch": "PyTorch",
    "numpy": "NumPy",
    "iou": "IoU",
    "cbow": "CBoW",
    "rnns": "RNNs（循环神经网络）",
    "how do you choose the right classifier?": "如何选择合适的分类器？",
    "educated guess and check": "基于经验进行猜测并验证",
    "both of the above": "以上两者都是",
    "decision trees": "决策树",
    "one-vs-all multiclass": "一对多多分类",
}

TERM_REPLACEMENTS = {
    "美国有线电视新闻网": "CNN（卷积神经网络）",
    "克尼恩": "KNN（K近邻）",
    "阿里玛": "ARIMA",
    "数学图书馆": "数学库",
    "RBF内核": "RBF核函数",
    "RBF 内核": "RBF核函数",
    "支持向量回归器": "支持向量回归",
}


def stable_id(prefix: str, *parts: str) -> str:
    raw = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:20]}"


def content_hash(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def sql_text(value: Any) -> str:
    if value is None:
        return "NULL"
    return "'" + str(value).replace("'", "''") + "'"


def sql_json(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sql_text(rendered) + "::jsonb"


def read_items(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_mapping(path: Path) -> Dict[str, Dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return {row["learning_item_id"]: row for row in csv.DictReader(stream)}


def translated_text(payload: Any) -> str:
    return "".join(segment[0] for segment in payload[0]).strip()


def translate_fields(fields: List[str], attempts: int = 4) -> List[str]:
    query = f"\n{SEPARATOR}\n".join(fields)
    params = urllib.parse.urlencode({
        "client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": query,
    })
    url = "https://translate.googleapis.com/translate_a/single?" + params
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "question-bank-localizer/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                result = translated_text(json.loads(response.read().decode("utf-8")))
            parts = [part.strip() for part in result.split(SEPARATOR)]
            if len(parts) != len(fields) or any(not part for part in parts):
                raise ValueError(f"translation field count mismatch: {len(parts)} != {len(fields)}")
            return parts
        except Exception as exc:  # network retry boundary
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"translation failed after {attempts} attempts: {last_error}")


def normalize_translation(source: str, translated: str) -> str:
    exact = EXACT_TRANSLATIONS.get(source.strip().casefold())
    if exact:
        return exact
    value = translated.strip()
    for wrong, right in TERM_REPLACEMENTS.items():
        value = value.replace(wrong, right)
    # Preserve short all-capital technical acronyms that machine translation
    # may transliterate. Longer phrases still keep their Chinese explanation.
    if re.fullmatch(r"[A-Z][A-Z0-9+.-]{1,9}", source.strip()):
        return EXACT_TRANSLATIONS.get(source.strip().casefold(), source.strip())
    return value


def explanation_for(
    stem_en: str,
    stem_zh: str,
    options: List[Dict[str, Any]],
    translated_options: List[str],
    knowledge_name_zh: str,
    source_url: str,
) -> Dict[str, Any]:
    correct_index = next(index for index, option in enumerate(options) if option.get("is_correct") is True)
    correct_key = str(options[correct_index]["key"])
    correct_text = translated_options[correct_index]
    normalized = stem_en.casefold()
    if "___" in stem_en or "____" in stem_en or "fill" in normalized:
        correct_reason = f"根据“{knowledge_name_zh}”相关术语，题干空缺应填“{correct_text}”。"
    elif correct_text.casefold() in {"true", "false", "正确", "错误", "真", "假"}:
        truth = correct_text.casefold() in {"true", "正确", "真"}
        correct_reason = (
            f"该陈述与课程中“{knowledge_name_zh}”的说明"
            f"{'一致' if truth else '不一致'}，因此应选择“{correct_text}”。"
        )
    else:
        correct_reason = f"在给定选项中，“{correct_text}”最符合题干对“{knowledge_name_zh}”的描述或条件。"
    option_reasons = {}
    for option, translated in zip(options, translated_options):
        key = str(option["key"])
        option_reasons[key] = (
            correct_reason if key == correct_key
            else f"“{translated}”不是本题参考答案；审核时需结合原课程补充它与正确选项的具体差异。"
        )
    return {
        "schemaVersion": "quiz-explanation.v1",
        "summary": f"本题考查“{knowledge_name_zh}”，参考答案为 {correct_key}：“{correct_text}”。",
        "correctOptionKey": correct_key,
        "correctReason": correct_reason,
        "optionReasons": option_reasons,
        "memoryTip": f"复习“{knowledge_name_zh}”时，先定位题干关键词，再逐项核对定义和适用条件。",
        "sourceUrls": [source_url],
        "generationMethod": "machine_translation_plus_structural_template",
        "generationVersion": PROVIDER_VERSION,
        "quality": "structural_draft",
        "requiresSubjectMatterReview": True,
        "originalStem": stem_en,
        "localizedStem": stem_zh,
    }


def build_row(item: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, str]:
    options = item["options"]
    fields = [item["stem"], *[str(option["text"]) for option in options], mapping["knowledge_point_name"]]
    translated = translate_fields(fields)
    stem_zh = normalize_translation(item["stem"], translated[0])
    option_zh = [
        normalize_translation(str(option["text"]), value)
        for option, value in zip(options, translated[1:1 + len(options)])
    ]
    knowledge_name_zh = normalize_translation(mapping["knowledge_point_name"], translated[-1])
    version_id = mapping["learning_item_version_id"]
    explanation = explanation_for(
        item["stem"], stem_zh, options, option_zh, knowledge_name_zh, item["source"]["source_url"]
    )
    by_key_en = {str(option["key"]).upper(): str(option["text"]) for option in options}
    by_key_zh = {str(option["key"]).upper(): text for option, text in zip(options, option_zh)}
    return {
        "learning_item_id": item["learning_item_id"],
        "learning_item_version_id": version_id,
        "source_id": item["source"]["source_id"],
        "source_file_path": item["source"]["file_path"],
        "source_item_key": item["source_item_key"],
        "source_commit": item["source"]["commit_sha"],
        "source_content_hash": item["source"]["content_hash"],
        "knowledge_point_id": mapping["knowledge_point_id"],
        "knowledge_point_name_en": mapping["knowledge_point_name"],
        "knowledge_point_name_zh": knowledge_name_zh,
        "question_stem_en": item["stem"],
        "option_a_en": by_key_en.get("A", ""),
        "option_b_en": by_key_en.get("B", ""),
        "option_c_en": by_key_en.get("C", ""),
        "correct_option_key": mapping["correct_option_key"],
        "zh_stem": stem_zh,
        "zh_option_a": by_key_zh.get("A", ""),
        "zh_option_b": by_key_zh.get("B", ""),
        "zh_option_c": by_key_zh.get("C", ""),
        "zh_explanation": explanation["summary"],
        "explanation_data_json": json.dumps(explanation, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "translation_method": PROVIDER,
        "translation_version": PROVIDER_VERSION,
        "translation_review_status": "pending",
        "explanation_review_status": "pending",
        "publish_decision": "hold",
        "reviewer_id": "",
        "reviewer_note": "",
    }


def normalize_existing_row(
    row: Dict[str, str], item: Dict[str, Any], mapping: Dict[str, str]
) -> Dict[str, str]:
    normalized = dict(row)
    normalized["zh_stem"] = normalize_translation(item["stem"], row["zh_stem"])
    translated_options: List[str] = []
    for option in item["options"]:
        key = str(option["key"]).lower()
        column = f"zh_option_{key}"
        normalized[column] = normalize_translation(str(option["text"]), row[column])
        translated_options.append(normalized[column])
    normalized["knowledge_point_name_zh"] = normalize_translation(
        mapping["knowledge_point_name"], row["knowledge_point_name_zh"]
    )
    explanation = explanation_for(
        item["stem"], normalized["zh_stem"], item["options"], translated_options,
        normalized["knowledge_point_name_zh"], item["source"]["source_url"],
    )
    normalized["zh_explanation"] = explanation["summary"]
    normalized["explanation_data_json"] = json.dumps(
        explanation, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return normalized


def seed_sql(rows: Iterable[Dict[str, str]], items_by_id: Dict[str, Dict[str, Any]]) -> str:
    lines = [
        "-- Generated zh-CN translation and explanation candidates; never auto-published.",
        "BEGIN;",
    ]
    for row in rows:
        version_id = row["learning_item_version_id"]
        locale_id = stable_id("item-localization", version_id, LOCALE)
        explanation = json.loads(row["explanation_data_json"])
        loc_hash = content_hash(row["zh_stem"], row["explanation_data_json"])
        lines.append(
            "INSERT INTO learning_item_localizations "
            "(learning_item_localization_id, learning_item_version_id, locale, stem, explanation, status, "
            "source_locale, translation_method, translation_version, explanation_data, explanation_status, content_hash) VALUES ("
            f"{sql_text(locale_id)}, {sql_text(version_id)}, {sql_text(LOCALE)}, {sql_text(row['zh_stem'])}, "
            f"{sql_text(row['zh_explanation'])}, 'needs_review', 'en', {sql_text(row['translation_method'])}, "
            f"{sql_text(row['translation_version'])}, {sql_json(explanation)}, 'needs_review', {sql_text(loc_hash)}) "
            "ON CONFLICT (learning_item_version_id, locale) DO NOTHING;"
        )
        item = items_by_id[row["learning_item_id"]]
        for index, option in enumerate(item["options"]):
            key = str(option["key"]).upper()
            translated = row[f"zh_option_{key.lower()}"]
            option_id = stable_id("option", version_id, str(index), str(option["key"]))
            option_loc_id = stable_id("option-localization", option_id, LOCALE)
            lines.append(
                "INSERT INTO item_option_localizations "
                "(item_option_localization_id, item_option_id, locale, option_text, status, "
                "translation_method, translation_version, content_hash) VALUES ("
                f"{sql_text(option_loc_id)}, {sql_text(option_id)}, {sql_text(LOCALE)}, {sql_text(translated)}, "
                f"'needs_review', {sql_text(row['translation_method'])}, {sql_text(row['translation_version'])}, "
                f"{sql_text(content_hash(translated))}) ON CONFLICT (item_option_id, locale) DO NOTHING;"
            )
    lines.extend(["COMMIT;", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--mappings", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--overwrite-review", action="store_true")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    items = [item for item in read_items(args.items) if item["item_type"] == "quiz_question"]
    if len(items) != 301:
        raise SystemExit(f"expected 301 Quiz items, got {len(items)}")
    mappings = read_mapping(args.mappings)
    review_path = args.output_dir / "quiz_localization_zh_review.csv"
    existing: Dict[str, Dict[str, str]] = {}
    if review_path.exists() and not args.overwrite_review:
        with review_path.open(encoding="utf-8", newline="") as stream:
            existing = {row["learning_item_id"]: row for row in csv.DictReader(stream)}

    rows_by_id: Dict[str, Dict[str, str]] = dict(existing)
    pending = [item for item in items if item["learning_item_id"] not in existing]
    if pending:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
            jobs = {
                executor.submit(build_row, item, mappings[item["learning_item_id"]]): item["learning_item_id"]
                for item in pending
            }
            completed = 0
            for job in as_completed(jobs):
                item_id = jobs[job]
                rows_by_id[item_id] = job.result()
                completed += 1
                if completed % 25 == 0 or completed == len(pending):
                    print(f"translated {completed}/{len(pending)} missing Quiz items", flush=True)

    rows = [
        normalize_existing_row(
            rows_by_id[item["learning_item_id"]], item, mappings[item["learning_item_id"]]
        )
        for item in items
    ]
    with review_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    items_by_id = {item["learning_item_id"]: item for item in items}
    (args.output_dir / "localization_seed.sql").write_text(seed_sql(rows, items_by_id), encoding="utf-8")
    report = {
        "schema_version": "quiz-localization-report.v1",
        "locale": LOCALE,
        "quiz_count": len(rows),
        "translated_stem_count": sum(bool(row["zh_stem"].strip()) for row in rows),
        "translated_option_set_count": sum(
            bool(row["zh_option_a"].strip() and row["zh_option_b"].strip()) for row in rows
        ),
        "explanation_candidate_count": sum(bool(row["explanation_data_json"].strip()) for row in rows),
        "translation_review_counts": {"pending": len(rows)},
        "explanation_review_counts": {"pending": len(rows)},
        "ready_to_publish_count": 0,
        "translation_method": PROVIDER,
        "translation_version": PROVIDER_VERSION,
        "warning": "Machine-generated candidates require subject-matter review before publication.",
    }
    (args.output_dir / "localization_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(rows)} zh-CN candidate rows to {review_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
