from dataclasses import dataclass
from pathlib import Path

from modules.common import api as common_api
from modules.diagnosis.agent import DiagnosticAgent
from modules.diagnosis.question_bank import QuestionBank
from modules.diagnosis.diagnosis_workflow import AssessmentService, DiagnosticSessionStore, DiagnosisWorkflow
from modules.learner_profile.workflow import JsonLearnerProfileRepository, LearnerProfileWorkflow
from modules.learning_plan.module import LearningPlanModule
from modules.learning_plan.agent import LearningPlanAgent
from modules.learning_record.module import LearningRecordModule
from modules.today_learning.module import TodayLearningModule
from modules.memory.module import MemoryModule
from modules.memory.repository import JsonMemoryRepository
from modules.material_qa.retriever import QdrantMaterialRetriever
from modules.material_qa.workflow import MaterialQaWorkflow
from sdk.llm_client import NullLLMClient


@dataclass(frozen=True)
class ApiDependencies:
    profile: LearnerProfileWorkflow
    diagnosis: DiagnosisWorkflow
    memory: MemoryModule
    learning_plan: LearningPlanModule
    material_qa: MaterialQaWorkflow
    learning_record: LearningRecordModule
    today_learning: TodayLearningModule

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
    profile_workflow = LearnerProfileWorkflow(profile_repository, memory=memory_module)
    question_repository = QuestionBank(settings.content_data_dir)
    learning_record_module = LearningRecordModule()
    session_repository = DiagnosticSessionStore()
    diagnosis_workflow = DiagnosisWorkflow(
        question_bank=question_repository,
        session_store=session_repository,
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(NullLLMClient()),
        memory=memory_module,
        learning_record=learning_record_module,
    )
    learning_plan_module = LearningPlanModule(session_repository, LearningPlanAgent(), memory=memory_module)
    today_learning_module = TodayLearningModule(learning_plan_module, learning_record_module, diagnosis_workflow)
    material_qa_retriever = QdrantMaterialRetriever(
        documents={
            "ml": settings.data_dir / "02-内容与数据" / "资料库" / "正式" / "ml-001",
            "dl": settings.data_dir / "02-内容与数据" / "资料库" / "正式" / "dl-001",
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
            activity_recorder=learning_record_module,
            retriever=material_qa_retriever,
        ),
        learning_record=learning_record_module,
        today_learning=today_learning_module,
    )


def build_diagnosis_workflow() -> tuple[DiagnosisWorkflow, DiagnosticSessionStore]:
    session_repository = DiagnosticSessionStore()
    workflow = DiagnosisWorkflow(
        question_bank=QuestionBank(common_api.config.Settings.from_env().content_data_dir),
        session_store=session_repository,
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(NullLLMClient()),
    )
    return workflow, session_repository
