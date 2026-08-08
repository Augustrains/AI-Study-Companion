from typing import Any, TypedDict


class LearnerProfileState(TypedDict, total=False):
    workflow_id: str
    raw_profile: dict[str, Any]
    draft_profile: dict[str, Any]
    review_action: str
    corrections: dict[str, Any]
    saved_profile: dict[str, Any]
    status: str
