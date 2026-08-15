from dataclasses import dataclass
from pathlib import Path

from modules.common import api as common_api
from modules.diagnosis.agent import DiagnosticAgent
from modules.diagnosis.services import AssessmentService, DiagnosisResultStore, GeneratedQuestionBank
from modules.diagnosis.workflow import DiagnosisWorkflow
from modules.learner_profile.workflow import JsonLearnerProfileRepository, LearnerProfileWorkflow
from modules.learning_plan.module import LearningPlanModule
from modules.learning_plan.agent import LearningPlanAgent
from modules.learning_record.module import LearningRecordModule
from modules.today_learning.module import TodayLearningModule
from modules.memory.module import MemoryModule
from modules.memory.repository import JsonMemoryRepository
from modules.material_qa.agent import MaterialQaAgent
from modules.material_qa.services import QdrantMaterialRetriever
from modules.material_qa.workflow import MaterialQaWorkflow
from sdk.llm_client import DeepSeekLLMClient


@dataclass(frozen=True)
class ApiDependencies:
    profile: LearnerProfileWorkflow
    diagnosis: DiagnosisWorkflow
    memory: MemoryModule
    learning_plan: LearningPlanModule
    material_qa: MaterialQaWorkflow
    learning_record: LearningRecordModule
    today_learning: TodayLearningModule

    def start(self) -> None:
        """预热应用级资源，避免首个请求承担模型加载成本。"""

        self.material_qa.start()

    def close(self) -> None:
        """关闭应用级资源，尤其是 Qdrant 本地存储客户端。"""

        self.material_qa.close()


def build_api_dependencies(settings: common_api.config.Settings | None = None) -> ApiDependencies:
    settings = settings or common_api.config.Settings.from_env()
    profile_reader = common_api.json_storage.JsonContentReader(
        settings.profile_path
    )
    profile_repository = JsonLearnerProfileRepository(
        profile_reader,
        common_api.json_storage.JsonStore(),
    )
    memory_reader = common_api.json_storage.JsonContentReader(settings.memory_path)
    memory_module = MemoryModule(
        JsonMemoryRepository(
            reader=memory_reader,
            store=common_api.json_storage.JsonStore(),
        )
    )
    knowledge_point_catalog = common_api.knowledge_points.JsonKnowledgePointCatalog(settings.knowledge_points_dir)
    profile_workflow = LearnerProfileWorkflow(
        profile_repository,
        memory=memory_module,
        knowledge_point_catalog=knowledge_point_catalog,
    )
    question_repository = GeneratedQuestionBank(settings.question_new_dir)
    learning_record_module = LearningRecordModule()
    result_repository = DiagnosisResultStore()
    diagnosis_workflow = DiagnosisWorkflow(
        question_bank=question_repository,
        result_store=result_repository,
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(DeepSeekLLMClient.from_env()),
        memory=memory_module,
        learning_record=learning_record_module,
        knowledge_point_catalog=knowledge_point_catalog,
    )
    learning_plan_module = LearningPlanModule(
        result_repository,
        LearningPlanAgent(DeepSeekLLMClient.from_env()),
        memory=memory_module,
        learner_profile=profile_workflow,
    )
    today_learning_module = TodayLearningModule(learning_plan_module, learning_record_module, diagnosis_workflow)
    material_qa_retriever = QdrantMaterialRetriever(
        documents={
            "ml": settings.new_material_dir / "ML-For-Beginners" / "lessons",
            "dl": settings.new_material_dir / "AI-For-Beginners" / "lessons",
        },
        qdrant_path=settings.qdrant_path,
        embedding_model=settings.embedding_model,
    )

    return ApiDependencies(
        profile=profile_workflow,
        diagnosis=diagnosis_workflow,
        memory=memory_module,
        learning_plan=learning_plan_module,
        material_qa=MaterialQaWorkflow(
            agent=MaterialQaAgent(DeepSeekLLMClient.from_env()),
            activity_recorder=learning_record_module,
            retriever=material_qa_retriever,
        ),
        learning_record=learning_record_module,
        today_learning=today_learning_module,
    )


def build_diagnosis_workflow() -> tuple[DiagnosisWorkflow, DiagnosisResultStore]:
    result_repository = DiagnosisResultStore()
    settings = common_api.config.Settings.from_env()
    workflow = DiagnosisWorkflow(
        question_bank=GeneratedQuestionBank(settings.question_new_dir),
        result_store=result_repository,
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(DeepSeekLLMClient.from_env()),
        knowledge_point_catalog=common_api.knowledge_points.JsonKnowledgePointCatalog(settings.knowledge_points_dir),
    )
    return workflow, result_repository
