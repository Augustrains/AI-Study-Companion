import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.algorithms.mastery_rules import calculate_mastery_update  # noqa: E402


class MasteryRuleTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 12, tzinfo=timezone.utc)

    def test_high_score_without_delayed_evidence_is_not_mastery(self):
        result = calculate_mastery_update(
            {
                "currentState": {
                    "masteryScore": 0.9,
                    "evidenceSummary": {"independentCorrectCount": 2},
                },
                "evidence": [
                    {
                        "evidenceId": "e-1",
                        "score": 1,
                        "isCorrect": True,
                        "taskMode": "independent",
                        "isIndependent": True,
                    }
                ],
            },
            self.now,
        )
        self.assertEqual(result["masteryLevel"], "熟悉")
        self.assertEqual(result["memoryStatus"], "首次验证")
        self.assertIn("MASTERY_GATE_NEEDS_INDEPENDENT_DELAYED_EVIDENCE", result["reasonCodes"])

    def test_mastery_requires_repeated_independent_and_delayed_success(self):
        result = calculate_mastery_update(
            {
                "currentState": {
                    "masteryScore": 0.9,
                    "evidenceSummary": {
                        "acceptedEvidenceCount": 2,
                        "effectiveEvidenceWeight": 2,
                        "independentCorrectCount": 2,
                        "delayedCorrectCount": 0,
                        "delayedFailureCount": 0,
                        "guidedEvidenceCount": 0,
                    },
                },
                "evidence": [
                    {
                        "evidenceId": "e-delayed",
                        "score": 1,
                        "isCorrect": True,
                        "taskMode": "retrieval",
                        "isIndependent": True,
                        "isDelayedRetrieval": True,
                        "scheduledIntervalDays": 4,
                    }
                ],
            },
            self.now,
        )
        self.assertEqual(result["masteryLevel"], "掌握")
        self.assertEqual(result["memoryStatus"], "延迟复测通过")
        self.assertEqual(result["evidenceIds"], ["e-delayed"])

    def test_guidance_and_retries_are_discounted(self):
        plain = calculate_mastery_update(
            {"evidence": [{"evidenceId": "plain", "score": 1, "isCorrect": True}]}, self.now
        )
        guided = calculate_mastery_update(
            {
                "evidence": [
                    {
                        "evidenceId": "guided",
                        "score": 1,
                        "isCorrect": True,
                        "taskMode": "guided_practice",
                        "hintCount": 2,
                        "retryCount": 1,
                    }
                ]
            },
            self.now,
        )
        self.assertLess(guided["masteryScore"], plain["masteryScore"])

    def test_example_input_is_valid(self):
        payload = json.loads((ROOT / "interfaces/examples/mastery-update-input.json").read_text())
        result = calculate_mastery_update(payload, self.now)
        self.assertTrue(result["evidenceIds"])
        self.assertEqual(result["algorithmVersion"], "1.0.0")


if __name__ == "__main__":
    unittest.main()
