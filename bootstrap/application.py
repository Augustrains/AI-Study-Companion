from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.engine import Engine

from modules.common import api as common_api
from modules.diagnosis.agent import DiagnosticAgent
from modules.diagnosis.services import AssessmentService, DiagnosisResultStore, GeneratedQuestionBank
from modules.diagnosis.workflow import DiagnosisWorkflow
from modules.diagnosis.repository import MySqlDiagnosisRepository
from modules.learner_profile.agent import CurrentMasteryAssessmentAgent, GoalKnowledgeRequirementAgent
from modules.learner_profile.module import MySqlLearnerProfileModule
from modules.learner_profile.repository import MySqlLearnerProfileRepository
from modules.common.database import check_mysql_connection, create_mysql_engine
from modules.auth.module import AuthModule
from modules.auth.repository import MysqlAccountStore
from modules.diagnosis.agent import DiagnosticAgent
from modules.diagnosis.services import AssessmentService, DiagnosisResultStore, GeneratedQuestionBank
from modules.diagnosis.workflow import DiagnosisWorkflow
from modules.learner_goals.module import LearnerGoalModule
from modules.learner_goals.repository import MysqlLearnerGoalRepository
from modules.learning_plan.module import LearningPlanModule
from modules.learning_plan.pace import LearningPaceAgent
from modules.learning_plan.repository import MySqlLearningPlanRepository
from modules.learning_record.module import LearningRecordModule
from modules.material_qa.agent import MaterialQaAgent
from modules.material_qa.services import MarkdownMaterialRetriever, QdrantMaterialRetriever, ResilientMaterialRetriever
from modules.material_qa.repository import MysqlMaterialQaMessageStore
from modules.material_qa.services import QdrantMaterialRetriever
from modules.material_qa.workflow import MaterialQaWorkflow
from modules.material_qa.attachment_repository import MysqlMaterialQaAttachmentRepository
from modules.material_qa.attachment_service import MaterialQaAttachmentService
from modules.material_qa.attachment_storage import OssAttachmentStorage
from modules.today_learning.module import TodayLearningModule
from sdk.llm_client import DeepSeekLLMClient


@dataclass(frozen=True)
class ApiDependencies:
    profile: MySqlLearnerProfileModule
    diagnosis: DiagnosisWorkflow
    learning_plan: LearningPlanModule
    material_qa: MaterialQaWorkflow
    material_qa_attachments: MaterialQaAttachmentService
    learning_record: LearningRecordModule
    today_learning: TodayLearningModule
    # 学习目标：只读写本地 JSON，没有需要预热或关闭的资源。
    learner_goals: LearnerGoalModule
    # 认证：同上，启动时会确保体验账号存在。
    auth: AuthModule
    database_engine: Engine

    def start(self) -> None:
        """Warm the database pool so the first learner request avoids a slow remote handshake."""
        try:
            check_mysql_connection(self.database_engine)
        except Exception:
            # 连接恢复由 SQLAlchemy 的 pool_pre_ping 处理；不要因预热失败阻止 API 启动。
            pass

    def close(self) -> None:
        """关闭应用级资源，尤其是 Qdrant 本地存储客户端。"""

        self.material_qa.close()
        self.database_engine.dispose()


def build_api_dependencies(settings: common_api.config.Settings | None = None) -> ApiDependencies:
    settings = settings or common_api.config.Settings.from_env()
    database_engine = create_mysql_engine(settings)
    knowledge_point_catalog = common_api.knowledge_points.JsonKnowledgePointCatalog(settings.knowledge_points_dir)
    profile_workflow = MySqlLearnerProfileModule(
        MySqlLearnerProfileRepository.from_env(),
        GoalKnowledgeRequirementAgent(DeepSeekLLMClient.from_env()),
        CurrentMasteryAssessmentAgent(DeepSeekLLMClient.from_env()),
    )
    question_repository = GeneratedQuestionBank(settings.question_new_dir)
    learning_record_module = LearningRecordModule()
    result_repository = DiagnosisResultStore()
    learning_plan_module = LearningPlanModule(MySqlLearningPlanRepository.from_env(), pace_agent=LearningPaceAgent(learning_record_module))
    diagnosis_workflow = DiagnosisWorkflow(
        question_bank=question_repository,
        result_store=result_repository,
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(DeepSeekLLMClient.from_env()),
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
    learner_goal_module = LearnerGoalModule(
        repository=MysqlLearnerGoalRepository(database_engine)
    )
    today_learning_module = TodayLearningModule(learning_plan_module, learning_record_module, diagnosis_workflow)
    material_qa_attachment_service = MaterialQaAttachmentService(
        storage=OssAttachmentStorage.from_settings(settings),
        repository=MysqlMaterialQaAttachmentRepository(database_engine),
    )

    return ApiDependencies(
        profile=profile_workflow,
        diagnosis=diagnosis_workflow,
        learning_plan=learning_plan_module,
        material_qa=MaterialQaWorkflow(
            agent=MaterialQaAgent(DeepSeekLLMClient.from_env()),
            activity_recorder=learning_record_module,
            retriever=material_qa_retriever,
            message_store=MysqlMaterialQaMessageStore(database_engine),
            attachment_service=material_qa_attachment_service,
        ),
        material_qa_attachments=material_qa_attachment_service,
        learning_record=learning_record_module,
        today_learning=today_learning_module,
        learner_goals=learner_goal_module,
        auth=AuthModule(
            store=MysqlAccountStore(database_engine),
            seed_demo_account=False,
        ),
        database_engine=database_engine,
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
