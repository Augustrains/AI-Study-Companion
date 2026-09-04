"""Application composition root for the database-backed learning workflow."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.engine import Engine

from modules.common import api as common_api
from modules.common.database import create_mysql_engine
from modules.diagnosis.agent import DiagnosticAgent
from modules.diagnosis.repository import MySqlDiagnosisRepository
from modules.diagnosis.services import AssessmentService, DiagnosisResultStore, GeneratedQuestionBank
from modules.diagnosis.workflow import DiagnosisWorkflow
from modules.learner_profile.agent import CurrentMasteryAssessmentAgent, GoalKnowledgeRequirementAgent
from modules.learner_profile.module import MySqlLearnerProfileModule
from modules.learner_profile.repository import MySqlLearnerProfileRepository
from modules.learning_plan.module import LearningPlanModule
from modules.learning_plan.pace import LearningPaceAgent
from modules.learning_plan.repository import MySqlLearningPlanRepository
from modules.learning_record.module import LearningRecordModule
from modules.material_qa.agent import MaterialQaAgent
from modules.material_qa.repository import MysqlMaterialQaMessageStore
from modules.material_qa.services import MarkdownMaterialRetriever, QdrantMaterialRetriever, ResilientMaterialRetriever
from modules.material_qa.workflow import MaterialQaWorkflow
from sdk.llm_client import DeepSeekLLMClient


@dataclass(frozen=True)
class ApiDependencies:
    profile: MySqlLearnerProfileModule
    diagnosis: DiagnosisWorkflow
    learning_plan: LearningPlanModule
    material_qa: MaterialQaWorkflow
    learning_record: LearningRecordModule
    database_engine: Engine

    def start(self) -> None:
        """Preheat retrieval; use local Markdown if Qdrant cannot start."""
        self.material_qa.start()

    def close(self) -> None:
        self.material_qa.close()
        self.database_engine.dispose()


def build_api_dependencies(settings: common_api.config.Settings | None = None) -> ApiDependencies:
    """Create the one consistent MySQL-backed dependency graph used by the API."""
    settings = settings or common_api.config.Settings.from_env()
    database_engine = create_mysql_engine(settings)
    knowledge_point_catalog = common_api.knowledge_points.JsonKnowledgePointCatalog(
        settings.knowledge_points_dir
    )
    llm_client = DeepSeekLLMClient.from_env()
    learning_record_module = LearningRecordModule()

    profile_workflow = MySqlLearnerProfileModule(
        MySqlLearnerProfileRepository.from_env(),
        GoalKnowledgeRequirementAgent(llm_client),
        CurrentMasteryAssessmentAgent(llm_client),
    )
    learning_plan_module = LearningPlanModule(
        MySqlLearningPlanRepository.from_env(),
        pace_agent=LearningPaceAgent(learning_record_module),
    )
    diagnosis_workflow = DiagnosisWorkflow(
        question_bank=GeneratedQuestionBank(settings.question_new_dir),
        result_store=DiagnosisResultStore(),
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(llm_client),
        learning_record=learning_record_module,
        knowledge_point_catalog=knowledge_point_catalog,
        database_repository=MySqlDiagnosisRepository.from_env(),
        learning_plan=learning_plan_module,
    )

    material_documents = {
        "ml": settings.new_material_dir / "ML-For-Beginners",
        "dl": settings.new_material_dir / "AI-For-Beginners",
    }
    material_qa_retriever = ResilientMaterialRetriever(
        primary=QdrantMaterialRetriever(
            documents=material_documents,
            qdrant_path=settings.qdrant_path,
            embedding_model=settings.embedding_model,
        ),
        fallback=MarkdownMaterialRetriever(documents=material_documents),
    )

    return ApiDependencies(
        profile=profile_workflow,
        diagnosis=diagnosis_workflow,
        learning_plan=learning_plan_module,
        material_qa=MaterialQaWorkflow(
            agent=MaterialQaAgent(llm_client),
            activity_recorder=learning_record_module,
            retriever=material_qa_retriever,
            message_store=MysqlMaterialQaMessageStore(database_engine),
        ),
        learning_record=learning_record_module,
        database_engine=database_engine,
    )


def build_diagnosis_workflow() -> tuple[DiagnosisWorkflow, DiagnosisResultStore]:
    """Build the lightweight interactive diagnostic demo workflow."""
    result_repository = DiagnosisResultStore()
    settings = common_api.config.Settings.from_env()
    workflow = DiagnosisWorkflow(
        question_bank=GeneratedQuestionBank(settings.question_new_dir),
        result_store=result_repository,
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(DeepSeekLLMClient.from_env()),
        knowledge_point_catalog=common_api.knowledge_points.JsonKnowledgePointCatalog(
            settings.knowledge_points_dir
        ),
    )
    return workflow, result_repository
