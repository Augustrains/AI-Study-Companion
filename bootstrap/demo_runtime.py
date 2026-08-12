"""Minimal end-to-end diagnosis workflow demo."""

from modules.diagnosis.models import DiagnosticSession
from bootstrap.application import build_diagnosis_workflow


async def run_diagnosis_demo() -> None:
    workflow, session_repository = build_diagnosis_workflow()
    session = DiagnosticSession(
        id="diag_demo",
        user_id="user_001",
        book_id="machine_learning",
        learning_goal="熟悉",
    )

    started = workflow.start(session)
    draft = workflow.submit(started["diagnosis_id"], {
        "ml_q001": "0",
        "ml_q002": "0",
        "ml_q003": "0",
        "ml_q004": "1",
    })
    print(f"等待确认诊断: {draft['diagnosis_id']}")

    diagnosis = workflow.review(
        started["diagnosis_id"],
        action="edit",
        calibrations={"linear_regression": "基本了解"},
    )
    if diagnosis is None:
        print("用户拒绝了本次诊断")
        return

    print(f"诊断编号: {diagnosis.diagnosis_id}")
    for result in diagnosis.results:
        final_status = result.calibrated_status or result.ai_status
        print(f"{result.knowledge_point_id}: {final_status} ({result.correct}/{result.total}) - {result.explanation}")
    print(f"诊断会话状态: {session_repository.get(session.id).status}")
