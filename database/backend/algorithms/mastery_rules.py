#!/usr/bin/env python3
"""Deterministic, explainable reference updater for knowledge mastery.

This module does not write the database. It converts a current state plus new
evidence events into the payload accepted by apply_mastery_update(). The
database function remains responsible for ownership checks, idempotency,
history, and optimistic locking.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
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


@dataclass(frozen=True)
class EvidenceEvent:
    evidence_id: str
    score: float
    is_correct: bool | None
    evidence_strength: str = "direct"
    task_mode: str = "diagnostic"
    hint_count: int = 0
    retry_count: int = 0
    is_independent: bool = False
    is_delayed_retrieval: bool = False
    scheduled_interval_days: float | None = None
    occurred_at: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "EvidenceEvent":
        score = float(value["score"])
        if not 0 <= score <= 1:
            raise ValueError("evidence score must be between 0 and 1")
        strength = value.get("evidenceStrength", "direct")
        mode = value.get("taskMode", "diagnostic")
        if strength not in STRENGTH_WEIGHT:
            raise ValueError(f"unsupported evidenceStrength: {strength}")
        if mode not in MODE_WEIGHT:
            raise ValueError(f"unsupported taskMode: {mode}")
        hints = int(value.get("hintCount", 0))
        retries = int(value.get("retryCount", 0))
        if hints < 0 or retries < 0:
            raise ValueError("hintCount and retryCount must be non-negative")
        return cls(
            evidence_id=str(value["evidenceId"]),
            score=score,
            is_correct=value.get("isCorrect"),
            evidence_strength=strength,
            task_mode=mode,
            hint_count=hints,
            retry_count=retries,
            is_independent=bool(value.get("isIndependent", mode in {"independent", "retrieval"})),
            is_delayed_retrieval=bool(value.get("isDelayedRetrieval", mode == "retrieval")),
            scheduled_interval_days=(
                float(value["scheduledIntervalDays"])
                if value.get("scheduledIntervalDays") is not None
                else None
            ),
            occurred_at=value.get("occurredAt"),
        )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _effective_weight(event: EvidenceEvent) -> float:
    hint_penalty = 1.0 / (1.0 + 0.35 * event.hint_count)
    retry_penalty = 1.0 / (1.0 + 0.30 * event.retry_count)
    return STRENGTH_WEIGHT[event.evidence_strength] * MODE_WEIGHT[event.task_mode] * hint_penalty * retry_penalty


def _mastery_level(score: float, independent_correct: int, delayed_correct: int) -> str:
    if score < 0.20:
        return "不会"
    if score < 0.50:
        return "了解"
    if score < 0.75:
        return "熟悉"
    # A high score alone is insufficient: mastery requires repeated independent
    # success and at least one delayed retrieval success.
    if independent_correct >= 3 and delayed_correct >= 1:
        return "掌握"
    return "熟悉"


def _memory_state(independent_correct: int, delayed_correct: int, delayed_failure: int) -> tuple[str, float]:
    if independent_correct == 0:
        return "未验证", 0.0
    if delayed_correct == 0:
        return "首次验证", 1.0
    effective_delayed = max(0, delayed_correct - delayed_failure)
    stability = STABILITY_STEPS[min(effective_delayed + 1, len(STABILITY_STEPS) - 1)]
    if delayed_correct >= 2 and delayed_failure == 0:
        return "稳定保持", stability
    return "延迟复测通过", stability


def calculate_mastery_update(payload: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """Return a database update payload from current state and evidence.

    Input shape is documented in interfaces/examples/mastery-update-input.json.
    Existing evidence counters are carried in currentState.evidenceSummary so
    the result remains deterministic across incremental calls.
    """

    current = payload.get("currentState") or {}
    previous_score = float(current.get("masteryScore", 0.0))
    if not 0 <= previous_score <= 1:
        raise ValueError("current masteryScore must be between 0 and 1")
    summary = dict(current.get("evidenceSummary") or {})
    summary.setdefault("acceptedEvidenceCount", 0)
    summary.setdefault("effectiveEvidenceWeight", 0.0)
    summary.setdefault("independentCorrectCount", 0)
    summary.setdefault("delayedCorrectCount", 0)
    summary.setdefault("delayedFailureCount", 0)
    summary.setdefault("guidedEvidenceCount", 0)

    events = [EvidenceEvent.from_dict(value) for value in payload.get("evidence", [])]
    if not events:
        raise ValueError("at least one evidence event is required")
    if len({event.evidence_id for event in events}) != len(events):
        raise ValueError("evidenceId values must be unique")

    score = previous_score
    accepted_ids: list[str] = []
    reason_codes: set[str] = set()
    for event in sorted(events, key=lambda value: (value.occurred_at or "", value.evidence_id)):
        weight = _effective_weight(event)
        if weight <= 0:
            reason_codes.add("IGNORED_NON_MASTERY_EVIDENCE")
            continue
        alpha = min(0.50, 0.12 + 0.25 * weight)
        # Incorrect responses are allowed to lower an overestimated state a
        # little faster than a correct response raises it.
        if event.score < score:
            alpha = min(0.58, alpha * 1.15)
        score = _clamp(score + alpha * (event.score - score))
        accepted_ids.append(event.evidence_id)
        summary["acceptedEvidenceCount"] += 1
        summary["effectiveEvidenceWeight"] += weight
        if event.task_mode == "guided_practice":
            summary["guidedEvidenceCount"] += 1
            reason_codes.add("GUIDED_EVIDENCE_DISCOUNTED")
        if event.is_independent and event.score >= 0.70:
            summary["independentCorrectCount"] += 1
            reason_codes.add("INDEPENDENT_SUCCESS")
        if event.is_delayed_retrieval:
            if event.score >= 0.70:
                summary["delayedCorrectCount"] += 1
                reason_codes.add("DELAYED_RETRIEVAL_SUCCESS")
            else:
                summary["delayedFailureCount"] += 1
                reason_codes.add("DELAYED_RETRIEVAL_FAILURE")
        if event.hint_count or event.retry_count:
            reason_codes.add("SCAFFOLD_OR_RETRY_DISCOUNTED")

    if not accepted_ids:
        raise ValueError("no mastery-effective evidence remains after filtering")

    summary["effectiveEvidenceWeight"] = round(float(summary["effectiveEvidenceWeight"]), 4)
    independent_correct = int(summary["independentCorrectCount"])
    delayed_correct = int(summary["delayedCorrectCount"])
    delayed_failure = int(summary["delayedFailureCount"])
    level = _mastery_level(score, independent_correct, delayed_correct)
    memory_status, stability_days = _memory_state(independent_correct, delayed_correct, delayed_failure)
    confidence = min(0.99, 1.0 - math.exp(-float(summary["effectiveEvidenceWeight"]) / 4.0))
    if level == "掌握":
        reason_codes.add("MASTERY_GATE_SATISFIED")
    elif score >= 0.75:
        reason_codes.add("MASTERY_GATE_NEEDS_INDEPENDENT_DELAYED_EVIDENCE")

    now = now or datetime.now(timezone.utc)
    next_review = now + timedelta(days=max(1.0, stability_days))
    return {
        "masteryLevel": level,
        "masteryScore": round(score, 4),
        "memoryStatus": memory_status,
        "memoryStabilityDays": round(stability_days, 4),
        "confidence": round(confidence, 4),
        "evidenceIds": accepted_ids,
        "evidenceSummary": summary,
        "reasonCodes": sorted(reason_codes),
        "algorithmName": ALGORITHM_NAME,
        "algorithmVersion": ALGORITHM_VERSION,
        "nextReviewAt": next_review.isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an explainable mastery update payload")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = calculate_mastery_update(json.loads(args.input.read_text(encoding="utf-8")))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
