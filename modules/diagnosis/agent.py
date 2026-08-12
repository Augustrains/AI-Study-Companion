"""AI-facing interfaces for diagnostic interpretation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sdk.llm_client import LLMClient

@dataclass(frozen=True)
class DiagnosticAnalysisInput:
    """Complete, verified diagnostic facts supplied to the future AI call."""

    diagnosis_id: str
    learning_goal: str
    total_questions: int
    answered_questions: int
    skipped_questions: int
    correct_questions: int
    accuracy: float
    level: str
    confidence: str
    knowledge_point_results: list[dict[str, Any]] = field(default_factory=list)
    question_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class DiagnosticAnalysisOutput:
    """Text produced by the diagnostic AI interface."""

    evidence: str
    answer_performance: str


class DiagnosticAgent:
    """Generate learner-facing interpretations from verified diagnostic data."""

    DEFAULT_EVIDENCE = "目前证据来自默认字段"
    DEFAULT_ANSWER_PERFORMANCE = "目前作答表现来自默认字段"

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self.llm_client = llm_client

    async def analyze_performance(
        self,
        analysis_input: DiagnosticAnalysisInput,
    ) -> DiagnosticAnalysisOutput:
        """Return a placeholder until the real LLM implementation is connected."""
        del analysis_input
        return DiagnosticAnalysisOutput(
            evidence=self.DEFAULT_EVIDENCE,
            answer_performance=self.DEFAULT_ANSWER_PERFORMANCE,
        )
