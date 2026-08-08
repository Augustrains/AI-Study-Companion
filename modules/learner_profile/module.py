from __future__ import annotations

from typing import Any

from .models import LearnerProfile
from .repository import JsonLearnerProfileRepository
from .service import LearnerProfileService
from .workflow import LearnerProfileWorkflow


class LearnerProfileModule:
    """Application-facing facade for learner-profile use cases."""

    def __init__(
        self,
        repository: JsonLearnerProfileRepository,
        service: LearnerProfileService,
        workflow: LearnerProfileWorkflow,
    ) -> None:
        self.repository = repository
        self.service = service
        self.workflow = workflow

    def get(self, user_id: str, learning_domain: str | None = None) -> LearnerProfile | None:
        return self.repository.get(user_id, learning_domain)

    def start_workflow(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.workflow.start(payload)

    def review_workflow(
        self,
        workflow_id: str,
        *,
        action: str,
        corrections: dict[str, Any] | None = None,
    ) -> LearnerProfile | None:
        return self.workflow.review(workflow_id, action=action, corrections=corrections)
