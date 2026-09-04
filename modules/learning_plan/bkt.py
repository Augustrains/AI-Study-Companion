"""Small, deterministic BKT estimator used by the database-backed planner.

The estimator deliberately returns learning *opportunities*, rather than
pretending that a probability model can infer elapsed minutes.  The planner
converts opportunities to minutes with explicit, configurable task baselines.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, log
from typing import Iterable


@dataclass(frozen=True)
class BktEstimate:
    mastery_score: float
    predicted_correct_rate: float
    learning_rate: float
    expected_practice_count: int
    confidence: float


class BktMasteryEstimator:
    """Estimate practice opportunities with a lightweight individualized BKT.

    With sparse data, the model uses conservative population parameters.  As
    answer history grows, the observed correctness rate adjusts the per-user
    learning-transition rate.  This is intentionally deterministic so a plan
    can be regenerated and audited from the same database facts.
    """

    POPULATION_LEARN_RATE = 0.12
    GUESS_RATE = 0.20
    SLIP_RATE = 0.10
    # A BKT transition approaches 1 asymptotically.  A database score of 1.0
    # means "mastery goal", not literal certainty, so use a computable cap.
    PRACTICAL_TARGET_CAP = 0.98

    @staticmethod
    def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
        return max(lower, min(upper, value))

    def estimate(
        self,
        *,
        current_mastery: float,
        target_mastery: float,
        outcomes: Iterable[bool] = (),
        stored_confidence: float = 0.0,
    ) -> BktEstimate:
        answers = [bool(item) for item in outcomes]
        mastery = self._clamp(float(current_mastery))
        target = min(self._clamp(float(target_mastery)), self.PRACTICAL_TARGET_CAP)
        accuracy = sum(answers) / len(answers) if answers else None
        learning_rate = self.POPULATION_LEARN_RATE
        if accuracy is not None:
            # A bounded individual adjustment avoids overfitting a handful of
            # diagnostic answers while still distinguishing faster learners.
            learning_rate = self._clamp(
                self.POPULATION_LEARN_RATE + (accuracy - 0.5) * 0.12,
                0.06,
                0.24,
            )

        # Incorporate answer evidence only when generating the estimate.  We
        # do not write this posterior back here: replaying historical answers
        # on every plan generation would otherwise inflate mastery repeatedly.
        posterior = mastery
        for is_correct in answers:
            prior_after_learning = posterior + (1.0 - posterior) * learning_rate
            if is_correct:
                numerator = (1.0 - self.SLIP_RATE) * prior_after_learning
                denominator = numerator + self.GUESS_RATE * (1.0 - prior_after_learning)
            else:
                numerator = self.SLIP_RATE * prior_after_learning
                denominator = numerator + (1.0 - self.GUESS_RATE) * (1.0 - prior_after_learning)
            posterior = numerator / denominator if denominator else posterior

        predicted_correct = self.GUESS_RATE * (1.0 - posterior) + (1.0 - self.SLIP_RATE) * posterior
        if posterior >= target:
            opportunities = 0
        else:
            # Expected latent transition after n effective opportunities:
            # 1 - (1 - posterior) * (1 - learn_rate)^n >= target.
            opportunities = ceil(log((1.0 - target) / (1.0 - posterior)) / log(1.0 - learning_rate))
        confidence = self._clamp(max(float(stored_confidence), min(0.9, 0.25 + len(answers) * 0.05)))
        return BktEstimate(
            mastery_score=round(posterior, 4),
            predicted_correct_rate=round(predicted_correct, 4),
            learning_rate=round(learning_rate, 4),
            expected_practice_count=max(0, opportunities),
            confidence=round(confidence, 4),
        )
