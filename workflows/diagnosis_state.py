from typing import Any, TypedDict


class DiagnosisState(TypedDict, total=False):
    """一次诊断工作流的可持久化运行状态。"""

    workflow_run_id: str
    diagnosis_id: str
    learning_session_id: str
    user_id: str
    book_id: str
    learning_goal: str

    questions: list[dict[str, Any]]
    answers: dict[str, str]
    draft_results: list[dict[str, Any]]
    answer_records: list[dict[str, Any]]

    review_action: str
    calibrations: dict[str, str]
    status: str

