from repositories.learner_profile_repository import JsonLearnerProfileRepository
from domain.models import LearningSession
from bootstrap.application import build_diagnosis_workflow


async def run_diagnosis_demo() -> None:
    user_id = "user_001"
    profile = JsonLearnerProfileRepository().get(user_id, "machine_learning")
    if profile is None:
        raise RuntimeError("请先启动 Web 应用并创建机器学习画像")

    workflow, session_repository = build_diagnosis_workflow()
    session = LearningSession(
        id="learn_001",
        user_id=profile.user_id,
        book_id="machine_learning",
        learning_goal="熟悉",
        learner_profile=profile,
    )
    started = workflow.start(session)
    draft = workflow.submit(started["diagnosis_id"], {
        "ml_q001": "Supervised Learning",
        "ml_q002": "Supervised Learning",
        "ml_q003": "连续值",
        "ml_q004": "类别标签",
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
    print(f"用户确认后的状态: {session_repository.get(session.id).knowledge_states}")
