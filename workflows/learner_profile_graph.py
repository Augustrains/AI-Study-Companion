from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from domain.learner_profile import LearnerProfile
from domain.learner_profile_service import LearnerProfileService
from repositories.learner_profile_repository import JsonLearnerProfileRepository
from workflows.learner_profile_state import LearnerProfileState


def build_learner_profile_graph(
    *,
    repository: JsonLearnerProfileRepository,
    profile_service: LearnerProfileService,
    checkpointer: Any,
):
    def normalize_profile(state: LearnerProfileState) -> dict[str, Any]:
        profile = profile_service.build_profile(state["raw_profile"])
        return {"draft_profile": profile.to_dict(), "status": "pending_confirmation"}

    def wait_for_confirmation(state: LearnerProfileState) -> dict[str, Any]:
        decision = interrupt({
            "type": "learner_profile_review",
            "workflow_id": state["workflow_id"],
            "draft_profile": state["draft_profile"],
            "allowed_actions": ["approve", "edit", "reject"],
        })
        if not isinstance(decision, dict):
            raise ValueError("profile review must be a JSON object")
        action = str(decision.get("action", "")).strip()
        if action not in {"approve", "edit", "reject"}:
            raise ValueError(f"unsupported profile review action: {action}")
        corrections = decision.get("corrections") or {}
        if action == "edit":
            profile = profile_service.apply_corrections(state["draft_profile"], corrections)
            return {"review_action": action, "corrections": corrections, "draft_profile": profile.to_dict(), "status": "approved"}
        return {"review_action": action, "corrections": {}, "status": "rejected" if action == "reject" else "approved"}

    def route_after_review(state: LearnerProfileState) -> str:
        return "reject" if state["review_action"] == "reject" else "commit"

    def commit_profile(state: LearnerProfileState) -> dict[str, Any]:
        profile = LearnerProfile.from_dict(state["draft_profile"])
        saved = repository.save(profile)
        return {"saved_profile": saved.to_dict(), "status": "completed"}

    def reject_profile(_: LearnerProfileState) -> dict[str, Any]:
        return {"status": "rejected"}

    builder = StateGraph(LearnerProfileState)
    builder.add_node("normalize", normalize_profile)
    builder.add_node("wait_for_confirmation", wait_for_confirmation)
    builder.add_node("commit", commit_profile)
    builder.add_node("reject", reject_profile)
    builder.add_edge(START, "normalize")
    builder.add_edge("normalize", "wait_for_confirmation")
    builder.add_conditional_edges("wait_for_confirmation", route_after_review, {"commit": "commit", "reject": "reject"})
    builder.add_edge("commit", END)
    builder.add_edge("reject", END)
    return builder.compile(checkpointer=checkpointer)
