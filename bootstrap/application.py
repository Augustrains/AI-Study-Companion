from dataclasses import dataclass

from modules.common import api as common_api
from modules.common.auth import IdentityResolver
from modules.context.builder import ContextBuilder
from modules.context.summarizer import (
    ConversationSummaryManager,
    RuleBasedSummaryBackend,
)
from modules.context.trace import ContextTraceRepository
from modules.conversation.repository import SqlConversationRepository
from modules.conversation.service import ConversationService
from modules.diagnosis.agent import DiagnosticAgent
from modules.diagnosis.services import (
    AssessmentService,
    DiagnosisResultStore,
    GeneratedQuestionBank,
)
from modules.diagnosis.workflow import DiagnosisWorkflow
from modules.learner_profile.workflow import (
    JsonLearnerProfileRepository,
    LearnerProfileWorkflow,
)
from modules.learning_plan.agent import LearningPlanAgent
from modules.learning_plan.module import LearningPlanModule
from modules.learning_record.module import LearningRecordModule
from modules.material_qa.agent import MaterialQaAgent
from modules.material_qa.services import MaterialQaService, QdrantMaterialRetriever
from modules.material_qa.workflow import MaterialQaWorkflow
from modules.memory.legacy_migration import (
    migrate_legacy_memory_to_sql,
    migrate_legacy_profiles_to_context_memory,
)
from modules.memory.module import MemoryModule
from modules.memory.sql_repository import SqlMemoryRepository
from modules.persistence.checkpoints import CheckpointResource
from modules.persistence.database import Database
from modules.persistence.workflows import WorkflowSessionRepository
from modules.today_learning.module import TodayLearningModule
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
    identity: IdentityResolver
    database: Database
    checkpoints: CheckpointResource
    context_builder: ContextBuilder
    conversations: ConversationService

    def start(self) -> None:
        """预热应用级资源，避免首个请求承担模型加载成本。"""

        self.material_qa.start()

    def close(self) -> None:
        """关闭应用级资源，尤其是 Qdrant 本地存储客户端。"""

        try:
            self.material_qa.close()
        finally:
            try:
                self.checkpoints.close()
            finally:
                self.database.close()


def build_api_dependencies(
    settings: common_api.config.Settings | None = None,
) -> ApiDependencies:
    settings = settings or common_api.config.Settings.from_env()
    database = Database(
        settings.database_url,
        create_schema=settings.auto_create_schema,
    )
    checkpoints: CheckpointResource | None = None
    try:
        checkpoints = CheckpointResource.open(
            backend=settings.checkpoint_backend,
            url=settings.checkpoint_url,
        )
        dependencies = _build_api_dependencies(settings, database, checkpoints)
    except BaseException:
        if checkpoints is not None:
            checkpoints.close()
        database.close()
        raise
    return dependencies


def _build_api_dependencies(
    settings: common_api.config.Settings,
    database: Database,
    checkpoints: CheckpointResource,
) -> ApiDependencies:
    profile_reader = common_api.json_storage.JsonContentReader(settings.profile_path)
    profile_repository = JsonLearnerProfileRepository(
        profile_reader,
        common_api.json_storage.JsonStore(),
    )
    memory_module = MemoryModule(SqlMemoryRepository(database))
    if settings.memory_path.exists():
        migrate_legacy_memory_to_sql(
            database=database,
            memory=memory_module,
            memory_path=settings.memory_path,
        )
    if settings.profile_path.exists():
        migrate_legacy_profiles_to_context_memory(
            database=database,
            memory=memory_module,
            profiles_path=settings.profile_path,
        )
    conversations = ConversationService(SqlConversationRepository(database))
    context_builder = ContextBuilder(
        memory=memory_module,
        conversations=conversations,
        summary_manager=ConversationSummaryManager(
            service=conversations,
            backend=RuleBasedSummaryBackend(),
        ),
        traces=ContextTraceRepository(database),
    )
    workflow_sessions = WorkflowSessionRepository(database)
    identity = IdentityResolver(
        allow_dev_identity=settings.allow_dev_identity,
        dev_user_id=settings.dev_user_id,
        jwt_secret=settings.jwt_secret,
    )
    knowledge_point_catalog = common_api.knowledge_points.JsonKnowledgePointCatalog(
        settings.knowledge_points_dir
    )
    profile_workflow = LearnerProfileWorkflow(
        profile_repository,
        memory=memory_module,
        knowledge_point_catalog=knowledge_point_catalog,
        checkpointer=checkpoints.saver,
        workflow_sessions=workflow_sessions,
    )
    question_repository = GeneratedQuestionBank(settings.question_new_dir)
    learning_record_module = LearningRecordModule()
    result_repository = DiagnosisResultStore(database)
    diagnosis_workflow = DiagnosisWorkflow(
        question_bank=question_repository,
        result_store=result_repository,
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(DeepSeekLLMClient.from_env()),
        memory=memory_module,
        learning_record=learning_record_module,
        knowledge_point_catalog=knowledge_point_catalog,
        checkpointer=checkpoints.saver,
        context_builder=context_builder,
        workflow_sessions=workflow_sessions,
    )
    learning_plan_module = LearningPlanModule(
        result_repository,
        LearningPlanAgent(DeepSeekLLMClient.from_env()),
        memory=memory_module,
        learner_profile=profile_workflow,
        context_builder=context_builder,
    )
    today_learning_module = TodayLearningModule(
        learning_plan_module, learning_record_module, diagnosis_workflow
    )
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
            retriever=material_qa_retriever,
            qa_service=MaterialQaService(
                activity_recorder=learning_record_module,
                conversations=conversations,
            ),
            context_builder=context_builder,
        ),
        learning_record=learning_record_module,
        today_learning=today_learning_module,
        identity=identity,
        database=database,
        checkpoints=checkpoints,
        context_builder=context_builder,
        conversations=conversations,
    )


def build_diagnosis_workflow() -> tuple[DiagnosisWorkflow, DiagnosisResultStore]:
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
