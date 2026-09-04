"""Fuse explainable diagnostic evidence with BKT posterior estimates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .bkt import BktEstimate


@dataclass(frozen=True)
class FusedMasteryUpdate:
    mastery_score: float
    confidence: float
    next_review_at: str | None
    rule_weight: float


class MasteryFusion:
    """Keep BKT authoritative for probability while calibrating it with evidence quality."""

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def combine(self, *, bkt: BktEstimate, rule_update: dict[str, Any]) -> FusedMasteryUpdate:
        """Blend the two estimates without allowing a single rule result to overwrite BKT.

        ``mastery_rules`` confidence comes from evidence strength, hints, retries,
        independence and delayed retrieval.  It controls how much that evidence
        can move the BKT posterior in this one update.
        """

        rule_score = self._clamp(float(rule_update.get("mastery_score", bkt.mastery_score)))
        rule_confidence = self._clamp(float(rule_update.get("confidence", 0.0)))
        rule_weight = 0.15 + 0.35 * rule_confidence
        mastery_score = self._clamp((1.0 - rule_weight) * bkt.mastery_score + rule_weight * rule_score)
        confidence = self._clamp(1.0 - (1.0 - bkt.confidence) * (1.0 - rule_confidence))
        return FusedMasteryUpdate(
            mastery_score=round(mastery_score, 4),
            confidence=round(confidence, 4),
            next_review_at=rule_update.get("next_review_at"),
            rule_weight=round(rule_weight, 4),
        )
