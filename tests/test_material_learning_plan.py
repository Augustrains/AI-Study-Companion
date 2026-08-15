from modules.diagnosis.services import DiagnosticSessionStore
from modules.learning_plan.module import LearningPlanModule
from modules.learning_plan.schemas import GenerateLearningPlanResponse, MaterialLearningPlanRequest
from tests.test_support import test_directory


def test_material_source_creates_fixed_qa_review_task() -> None:
    payload = MaterialLearningPlanRequest.model_validate(
        {
            "bookId": "ml",
            "title": "复习监督学习",
            "goal": "理解监督学习的基本概念",
            "description": "复习资料问答中引用的章节。",
            "minutes": 20,
            "expectedCompletionDate": "2026-08-15",
            "resources": [
                {
                    "id": "source-1",
                    "type": "教材",
                    "title": "ml-unit-001",
                    "location": "lessons/ml-unit-001.md",
                    "excerpt": "监督学习使用带标签的数据进行训练。",
                    "bookId": "ml",
                    "chapterId": "ml-chapter-001",
                    "sectionId": "ml-section-001",
                    "contentUnitId": "ml-unit-001",
                    "knowledgePointIds": ["supervised_learning"],
                }
            ],
        }
    )

    with test_directory("material-learning-plan") as directory:
        module = LearningPlanModule(
            DiagnosticSessionStore(),
            path=directory / "plans.json",
        )
        plan = module.create_from_material(
            book_id=payload.book_id,
            title=payload.title,
            goal=payload.goal,
            description=payload.description,
            minutes=payload.minutes,
            expected_completion_date=payload.expected_completion_date,
            resources=[resource.model_dump() for resource in payload.resources],
        )

    response = GenerateLearningPlanResponse.model_validate(plan)
    assert response.tasks[0].type == "qa_review"
    assert plan["tasks"][0]["source"] == "material_qa"
    assert response.resources[0].type == "教材"
    assert response.resources[0].book_id == "ml"
