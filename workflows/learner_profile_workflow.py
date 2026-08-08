from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from domain.learner_profile import LearnerProfile
from domain.learner_profile_service import LearnerProfileService
from repositories.learner_profile_repository import JsonLearnerProfileRepository
from workflows.learner_profile_graph import build_learner_profile_graph


class LearnerProfileWorkflow:
    """Profile workflow facade: normalize, review, then replace persisted JSON."""

    def __init__(self, repository: JsonLearnerProfileRepository, profile_service: LearnerProfileService, checkpointer: Any | None = None) -> None:
        self.checkpointer = checkpointer or InMemorySaver()
        self.graph = build_learner_profile_graph(repository=repository, profile_service=profile_service, checkpointer=self.checkpointer)

    @staticmethod
    def _config(workflow_id: str) -> dict[str, dict[str, str]]:
        return {"configurable": {"thread_id": workflow_id}}

    @staticmethod
    def _interrupt_value(result: dict[str, Any]) -> dict[str, Any]:
        interrupts = result.get("__interrupt__", ())
        if not interrupts:
            raise RuntimeError("profile workflow did not pause for confirmation")
        return interrupts[0].value

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        workflow_id = f"profile_{uuid4().hex[:10]}"
        result = self.graph.invoke({"workflow_id": workflow_id, "raw_profile": payload, "status": "started"}, config=self._config(workflow_id))
        return self._interrupt_value(result)

    def review(self, workflow_id: str, *, action: str, corrections: dict[str, Any] | None = None) -> LearnerProfile | None:
        result = self.graph.invoke(Command(resume={"action": action, "corrections": corrections or {}}), config=self._config(workflow_id))
        if result["status"] == "rejected":
            return None
        return LearnerProfile.from_dict(result["saved_profile"])
