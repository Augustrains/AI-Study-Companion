"""根据答题证据计算知识点掌握状态。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any


ALGORITHM_NAME = "explainable-mastery-rules"
ALGORITHM_VERSION = "1.0.0"
STRENGTH_WEIGHT = {"none": 0.0, "auxiliary": 0.35, "direct": 1.0, "strong": 1.15}
MODE_WEIGHT = {
    "diagnostic": 1.0,
    "guided_practice": 0.65,
    "independent": 1.0,
    "retrieval": 1.15,
    "remediation": 0.75,
    "challenge": 1.1,
}
STABILITY_STEPS = (1.0, 2.0, 4.0, 7.0, 15.0, 30.0, 60.0)


def _validated_event(value: dict[str, Any]) -> dict[str, Any]:
    score = float(value["score"])
    strength = str(value.get("evidenceStrength", "direct"))
    mode = str(value.get("taskMode", "diagnostic"))
    hints = int(value.get("hintCount", 0))
    retries = int(value.get("retryCount", 0))
    if not 0 <= score <= 1:
        raise ValueError("evidence score must be between 0 and 1")
    if strength not in STRENGTH_WEIGHT:
        raise ValueError(f"unsupported evidenceStrength: {strength}")
    if mode not in MODE_WEIGHT:
        raise ValueError(f"unsupported taskMode: {mode}")
    if hints < 0 or retries < 0:
        raise ValueError("hintCount and retryCount must be non-negative")
    return {
        "evidence_id": str(value["evidenceId"]),
        "score": score,
        "strength": strength,
        "mode": mode,
        "hints": hints,
        "retries": retries,
        "independent": bool(value.get("isIndependent", mode in {"independent", "retrieval"})),
        "delayed": bool(value.get("isDelayedRetrieval", mode == "retrieval")),
        "occurred_at": value.get("occurredAt"),
    }


def _mastery_level(score: float, independent_correct: int, delayed_correct: int) -> str:
    if score < 0.20:
        return "不会"
    if score < 0.50:
        return "了解"
    if score < 0.75:
        return "熟悉"
    return "掌握" if independent_correct >= 3 and delayed_correct >= 1 else "熟悉"


def calculate_mastery_update(payload: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """用当前状态和本轮答题证据生成确定性的掌握度更新。"""

    current = payload.get("currentState") or {}
    score = float(current.get("masteryScore", 0.0))
    if not 0 <= score <= 1:
        raise ValueError("current masteryScore must be between 0 and 1")

    summary = dict(current.get("evidenceSummary") or {})
    for key, default in {
        "acceptedEvidenceCount": 0,
        "effectiveEvidenceWeight": 0.0,
        "independentCorrectCount": 0,
        "delayedCorrectCount": 0,
        "delayedFailureCount": 0,
        "guidedEvidenceCount": 0,
    }.items():
        summary.setdefault(key, default)

    events = [_validated_event(item) for item in payload.get("evidence", [])]
    if not events:
        raise ValueError("at least one evidence event is required")
    evidence_ids = [item["evidence_id"] for item in events]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("evidenceId values must be unique")

    accepted_ids: list[str] = []
    reasons: set[str] = set()
    for event in sorted(events, key=lambda item: (item["occurred_at"] or "", item["evidence_id"])):
        weight = (
            STRENGTH_WEIGHT[event["strength"]]
            * MODE_WEIGHT[event["mode"]]
            / (1.0 + 0.35 * event["hints"])
            / (1.0 + 0.30 * event["retries"])
        )
        if weight <= 0:
            reasons.add("IGNORED_NON_MASTERY_EVIDENCE")
            continue
        alpha = min(0.50, 0.12 + 0.25 * weight)
        if event["score"] < score:
            alpha = min(0.58, alpha * 1.15)
        score = max(0.0, min(1.0, score + alpha * (event["score"] - score)))
        accepted_ids.append(event["evidence_id"])
        summary["acceptedEvidenceCount"] += 1
        summary["effectiveEvidenceWeight"] += weight
        if event["mode"] == "guided_practice":
            summary["guidedEvidenceCount"] += 1
            reasons.add("GUIDED_EVIDENCE_DISCOUNTED")
        if event["independent"] and event["score"] >= 0.70:
            summary["independentCorrectCount"] += 1
            reasons.add("INDEPENDENT_SUCCESS")
        if event["delayed"]:
            key = "delayedCorrectCount" if event["score"] >= 0.70 else "delayedFailureCount"
            summary[key] += 1
            reasons.add("DELAYED_RETRIEVAL_SUCCESS" if event["score"] >= 0.70 else "DELAYED_RETRIEVAL_FAILURE")
        if event["hints"] or event["retries"]:
            reasons.add("SCAFFOLD_OR_RETRY_DISCOUNTED")

    if not accepted_ids:
        raise ValueError("no mastery-effective evidence remains after filtering")
    summary["effectiveEvidenceWeight"] = round(float(summary["effectiveEvidenceWeight"]), 4)
    independent = int(summary["independentCorrectCount"])
    delayed_correct = int(summary["delayedCorrectCount"])
    delayed_failure = int(summary["delayedFailureCount"])
    level = _mastery_level(score, independent, delayed_correct)
    if independent == 0:
        memory_status, stability = "未验证", 0.0
    elif delayed_correct == 0:
        memory_status, stability = "首次验证", 1.0
    else:
        stability = STABILITY_STEPS[min(max(0, delayed_correct - delayed_failure) + 1, len(STABILITY_STEPS) - 1)]
        memory_status = "稳定保持" if delayed_correct >= 2 and delayed_failure == 0 else "延迟复测通过"
    if level == "掌握":
        reasons.add("MASTERY_GATE_SATISFIED")
    elif score >= 0.75:
        reasons.add("MASTERY_GATE_NEEDS_INDEPENDENT_DELAYED_EVIDENCE")
    confidence = min(0.99, 1.0 - math.exp(-summary["effectiveEvidenceWeight"] / 4.0))
    next_review = (now or datetime.now(timezone.utc)) + timedelta(days=max(1.0, stability))
    return {
        "masteryLevel": level,
        "masteryScore": round(score, 4),
        "memoryStatus": memory_status,
        "memoryStabilityDays": round(stability, 4),
        "confidence": round(confidence, 4),
        "evidenceIds": accepted_ids,
        "evidenceSummary": summary,
        "reasonCodes": sorted(reasons),
        "algorithmName": ALGORITHM_NAME,
        "algorithmVersion": ALGORITHM_VERSION,
        "nextReviewAt": next_review.isoformat(),
    }
