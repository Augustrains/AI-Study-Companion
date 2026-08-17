from __future__ import annotations

from pathlib import Path

import pytest

from modules.common import api as common_api
from modules.common.errors import ResourceNotFoundError
from modules.context.builder import ContextBuilder
from modules.context.summarizer import (
    ConversationSummaryManager,
    RuleBasedSummaryBackend,
)
from modules.context.trace import ContextTraceRepository
from modules.conversation.repository import SqlConversationRepository
from modules.conversation.service import ConversationService
from modules.diagnosis.agent import DiagnosticAgent
from modules.diagnosis.models import (
    AnswerRecord,
    AnswerResult,
    DiagnosisResult,
    KnowledgePointResult,
    Question,
)
from modules.diagnosis.services import AssessmentService, DiagnosisResultStore
from modules.diagnosis.workflow import DiagnosisWorkflow
from modules.learner_profile.workflow import (
    JsonLearnerProfileRepository,
    LearnerProfileWorkflow,
)
from modules.learning_plan.agent import LearningPlanAgent
from modules.learning_plan.module import LearningPlanModule
from modules.material_qa.agent import MaterialQaAgent
from modules.material_qa.models import MaterialQaRetrievalResult
from modules.material_qa.services import MaterialQaService
from modules.material_qa.workflow import MaterialQaWorkflow
from modules.memory.module import MemoryModule
from modules.memory.sql_repository import SqlMemoryRepository
from modules.persistence.checkpoints import CheckpointResource
from modules.persistence.database import Database
from modules.persistence.workflows import WorkflowSessionRepository


def runtime_stack(path: Path):
    database = Database(f"sqlite+pysqlite:///{path}", create_schema=True)
    memory = MemoryModule(SqlMemoryRepository(database))
    conversations = ConversationService(SqlConversationRepository(database))
    context = ContextBuilder(
        memory=memory,
        conversations=conversations,
        summary_manager=ConversationSummaryManager(
            conversations,
            RuleBasedSummaryBackend(),
        ),
        traces=ContextTraceRepository(database),
    )
    return database, memory, conversations, context


class RoleAwareClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.messages: list[dict[str, str]] = []

    def generate(self, _prompt: str) -> str:
        raise AssertionError("runtime context must preserve system/user roles")

    def generate_messages(self, messages: list[dict[str, str]]) -> str:
        self.messages = messages
        return self.response


class TinyQuestionBank:
    def get_question_inventory(self, _book_id: str) -> dict[str, int]:
        return {"kp-1": 1}

    def get_questions(self, book_id: str, *, question_plan, **_kwargs):
        assert question_plan["kp-1"]["question_count"] == 1
        return (
            [
                Question(
                    id="q-1",
                    title="什么是监督学习？",
                    tag="kp-1",
                    book_id=book_id,
                    knowledge_point_ids=["kp-1"],
                    options=[
                        {"id": "A", "text": "使用标注数据"},
                        {"id": "B", "text": "不使用数据"},
                    ],
                )
            ],
            {"q-1": "A"},
        )


def test_diagnosis_runtime_uses_context_roles_and_owner_registry(
    tmp_path: Path,
) -> None:
    database, memory, _conversations, context = runtime_stack(
        tmp_path / "runtime.sqlite3"
    )
    client = RoleAwareClient(
        '{"selections":[{"knowledgePointId":"kp-1","questionCount":1,"taskMode":"diagnostic"}]}'
    )
    workflow = DiagnosisWorkflow(
        question_bank=TinyQuestionBank(),
        result_store=DiagnosisResultStore(database),
        assessment_service=AssessmentService(),
        diagnostic_agent=DiagnosticAgent(client),
        memory=memory,
        context_builder=context,
        workflow_sessions=WorkflowSessionRepository(database),
    )

    started = workflow.start_diagnosis(
        user_id="alice",
        book_id="ml-001",
        learning_goal="掌握监督学习",
    )

    assert [item["role"] for item in client.messages] == ["system", "user"]
    assert "context_data" in client.messages[1]["content"]
    assert "availableQuestionCount" in client.messages[1]["content"]
    assert "kp-1" in client.messages[1]["content"]
    with pytest.raises(ResourceNotFoundError):
        workflow.submit_answer(
            started["diagnostic_id"],
            "q-1",
            "A",
            actor_user_id="bob",
        )
    saved = workflow.submit_answer(
        started["diagnostic_id"],
        "q-1",
        "A",
        actor_user_id="alice",
    )
    assert saved["saved"] is True
    database.close()


def diagnosis_result(user_id: str = "alice") -> DiagnosisResult:
    question = Question(
        id="q-plan",
        title="什么是过拟合？",
        tag="kp-plan",
        book_id="ml-001",
        knowledge_point_ids=["kp-plan"],
        options=[
            {"id": "A", "text": "训练好但泛化差"},
            {"id": "B", "text": "始终正确"},
        ],
    )
    return DiagnosisResult(
        diagnosis_id="diag-plan",
        user_id=user_id,
        book_id="ml-001",
        learning_goal="理解过拟合",
        answer_result=AnswerResult(
            answer_records=[
                AnswerRecord(
                    question=question,
                    submitted_answer="B",
                    correct_answer="A",
                    is_correct=False,
                    skipped=False,
                )
            ],
            total_questions=1,
            answered_questions=1,
            skipped_questions=0,
            correct_questions=0,
            accuracy=0.0,
            confidence="high",
        ),
        results=[
            KnowledgePointResult(
                knowledge_point_id="kp-plan",
                ai_status="不会",
                correct=0,
                total=1,
            )
        ],
    )


def test_learning_plan_is_owned_and_uses_planning_context(tmp_path: Path) -> None:
    database, _memory, _conversations, context = runtime_stack(
        tmp_path / "plan.sqlite3"
    )
    results = DiagnosisResultStore(database)
    results.save(diagnosis_result())
    client = RoleAwareClient(
        '{"tasks":[{"abilityId":"knowledge:kp-plan","title":"复习过拟合",'
        '"type":"concept_review","minutes":20,"reason":"本轮回答错误",'
        '"description":"重新解释泛化差异"}],"advice":["完成后复测"]}'
    )
    module = LearningPlanModule(
        results,
        LearningPlanAgent(client),
        path=tmp_path / "plans.json",
        context_builder=context,
    )

    plan = module.generate(
        diagnostic_id="diag-plan",
        book_id="ml",
        goal="理解过拟合",
        user_id="alice",
    )

    assert plan["tasks"][0]["title"] == "复习过拟合"
    assert [item["role"] for item in client.messages] == ["system", "user"]
    assert module.get_saved(book_id="ml", user_id="alice") is not None
    assert module.get_saved(book_id="ml", user_id="bob") is None
    with pytest.raises(ResourceNotFoundError):
        module.generate(
            diagnostic_id="diag-plan",
            book_id="ml",
            goal="越权",
            user_id="bob",
        )
    with pytest.raises(ResourceNotFoundError):
        module.complete_task(
            user_id="bob",
            task_id=plan["tasks"][0]["id"],
            book_id="ml",
        )
    database.close()


class RecordingRetriever:
    def __init__(self) -> None:
        self.history = []

    def retrieve(self, *, history, **_kwargs):
        self.history = history
        return MaterialQaRetrievalResult(chunks=[])


class QaClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def generate(self, _prompt: str) -> str:
        raise AssertionError("material QA must preserve system/user roles")

    def generate_messages(self, messages: list[dict[str, str]]) -> str:
        self.messages = messages
        return '{"refused": true, "answer": "当前资料不足。"}'


def test_tutor_conversation_is_durable_bounded_and_user_scoped(tmp_path: Path) -> None:
    database_path = tmp_path / "conversation.sqlite3"
    database, _memory, conversations, context = runtime_stack(database_path)
    retriever = RecordingRetriever()
    client = QaClient()
    workflow = MaterialQaWorkflow(
        agent=MaterialQaAgent(client),
        retriever=retriever,
        qa_service=MaterialQaService(conversations=conversations),
        context_builder=context,
    )
    conversation = workflow.create_conversation(book_id="ml", user_id="alice")
    for index in range(20):
        conversations.append(
            conversation.conversation_id,
            actor_user_id="alice",
            role="user" if index % 2 == 0 else "assistant",
            content=f"历史消息 {index}",
            request_id=f"seed-{index}",
        )

    workflow.ask(
        conversation_id=conversation.conversation_id,
        book_id="ml",
        question="请继续解释",
        actor_user_id="alice",
    )

    assert len(retriever.history) <= 9
    assert any("结构化摘要" in item.content for item in retriever.history)
    assert [item["role"] for item in client.messages] == ["system", "user"]
    with pytest.raises(ResourceNotFoundError):
        workflow.ask(
            conversation_id=conversation.conversation_id,
            book_id="ml",
            question="越权读取",
            actor_user_id="bob",
        )
    database.close()

    reopened = Database(
        f"sqlite+pysqlite:///{database_path}",
        create_schema=True,
    )
    reopened_service = ConversationService(SqlConversationRepository(reopened))
    recovered = reopened_service.messages(
        conversation.conversation_id,
        actor_user_id="alice",
        book_id="ml",
    )
    assert len(recovered) == 22
    assert (
        reopened_service.summary(
            conversation.conversation_id,
            actor_user_id="alice",
        )
        is not None
    )
    reopened.close()


def test_profile_checkpoint_and_owner_survive_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "owners.sqlite3"
    checkpoint_path = tmp_path / "checkpoints.sqlite3"
    profile_path = tmp_path / "profiles.json"

    database = Database(f"sqlite+pysqlite:///{database_path}", create_schema=True)
    checkpoints = CheckpointResource.open(backend="sqlite", url=str(checkpoint_path))
    repository = JsonLearnerProfileRepository(
        common_api.json_storage.JsonContentReader(profile_path),
        common_api.json_storage.JsonStore(),
    )
    workflow = LearnerProfileWorkflow(
        repository,
        checkpointer=checkpoints.saver,
        workflow_sessions=WorkflowSessionRepository(database),
    )
    started = workflow.start_workflow(
        {
            "user_id": "alice",
            "learning_domain": "machine_learning",
            "background": "计算机基础",
            "self_assessed_level": "basic",
            "preferences": {
                "activity_types": ["reading", "quiz"],
                "content_style": "balanced",
                "difficulty": "adaptive",
                "session_duration_minutes": 30,
                "learning_frequency": "flexible",
            },
        }
    )
    workflow_id = started["workflow_id"]
    checkpoints.close()
    database.close()

    database = Database(f"sqlite+pysqlite:///{database_path}", create_schema=True)
    checkpoints = CheckpointResource.open(backend="sqlite", url=str(checkpoint_path))
    workflow = LearnerProfileWorkflow(
        repository,
        checkpointer=checkpoints.saver,
        workflow_sessions=WorkflowSessionRepository(database),
    )
    with pytest.raises(ResourceNotFoundError):
        workflow.review_workflow(
            workflow_id,
            action="approve",
            actor_user_id="bob",
        )
    profile = workflow.review_workflow(
        workflow_id,
        action="approve",
        actor_user_id="alice",
    )
    assert profile is not None
    assert profile.user_id == "alice"
    checkpoints.close()
    database.close()
