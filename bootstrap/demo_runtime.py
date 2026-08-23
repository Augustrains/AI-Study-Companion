"""Minimal end-to-end diagnosis workflow demo."""

from bootstrap.application import build_diagnosis_workflow


async def run_diagnosis_demo() -> None:
    workflow, result_repository = build_diagnosis_workflow()
    started = workflow.start_diagnosis(
        user_id="user_001",
        book_id="machine_learning",
        learning_goal="熟悉机器学习基础",
    )
    for question in started["questions"]:
        workflow.submit_answer(
            started["diagnostic_id"],
            question["id"],
            question["options"][0]["id"],
        )
    await workflow.finish_diagnosis(started["diagnostic_id"])
    diagnosis = workflow.confirm_diagnosis(
        started["diagnostic_id"],
        calibration="same",
    )
    if diagnosis is None:
        print("用户拒绝了本次诊断")
        return

    print(f"诊断编号: {diagnosis.diagnosis_id}")
    for result in diagnosis.results:
        final_status = result.calibrated_status or result.ai_status
        print(f"{result.knowledge_point_id}: {final_status} ({result.correct}/{result.total})")
    print(f"已保存诊断结果: {result_repository.get(diagnosis.diagnosis_id).diagnosis_id}")
