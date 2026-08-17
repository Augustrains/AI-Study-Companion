from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from modules.context.builder import ContextBuilder
from modules.context.models import ContextMode
from modules.context.policies import ContextPolicyRegistry
from modules.context.summarizer import (
    ConversationSummaryManager,
    RuleBasedSummaryBackend,
)
from modules.context.trace import ContextTraceRepository
from modules.conversation.repository import SqlConversationRepository
from modules.conversation.service import ConversationService
from modules.material_qa.agent import MaterialQaAgent
from modules.material_qa.models import (
    MaterialQaRetrievalResult,
    MaterialQaRetrievedChunk,
)
from modules.material_qa.schemas import MaterialQaSource
from modules.material_qa.services import MaterialQaService
from modules.material_qa.workflow import MaterialQaWorkflow
from modules.memory.models import KnowledgePointMemory, LearnerMemory
from modules.memory.module import MemoryModule
from modules.memory.sql_repository import SqlMemoryRepository
from modules.persistence.database import Database
from modules.persistence.tables import ContextTraceRow


class RecordingRoleClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] = []

    def generate(self, _prompt: str) -> str:
        raise AssertionError("tutor context must preserve system/user roles")

    def generate_messages(self, messages: list[dict[str, str]]) -> str:
        self.messages = messages
        return '{"refused": false, "answer": "已结合资料和学习状态回答。"}'


class FiveChunkRetriever:
    def __init__(self) -> None:
        self.history = []

    def retrieve(self, *, history, **_kwargs) -> MaterialQaRetrievalResult:
        self.history = list(history)
        chunks = []
        for index in range(5):
            source = MaterialQaSource(
                id=f"source-{index}",
                type="教材",
                title=f"资料 {index}",
                location=f"第 {index + 1} 节",
                excerpt="资料摘要",
                knowledgePointIds=["kp-0"],
                bookId="ml",
            )
            chunks.append(
                MaterialQaRetrievedChunk(
                    text="中" * 1200,
                    source=source,
                    score=1.0 - index / 10,
                )
            )
        return MaterialQaRetrievalResult(chunks=chunks)


def _payload(user_message: str) -> dict:
    prefix = "<context_data>\n"
    suffix = "\n</context_data>"
    assert user_message.startswith(prefix)
    assert user_message.endswith(suffix)
    return json.loads(user_message[len(prefix) : -len(suffix)])


def test_tutor_final_prompt_keeps_recent_dialogue_and_fits_rag_context(
    tmp_path: Path,
) -> None:
    database = Database(
        f"sqlite+pysqlite:///{tmp_path / 'tutor-budget.sqlite3'}",
        create_schema=True,
    )
    memory_repository = SqlMemoryRepository(database)
    memory_repository.upsert(
        LearnerMemory(
            user_id="alice",
            learning_domain="ml-001",
            knowledge_points=[
                KnowledgePointMemory(
                    knowledge_point_id=f"kp-{index}",
                    mastery_level="了解",
                    assessed_mastery_level="了解",
                    mastery_score=0.4,
                    confidence=0.8,
                    source="diagnostic:seed",
                )
                for index in range(40)
            ],
            preferences={
                "content_style": "visual",
                "session_duration_minutes": 30,
            },
            current_confusions="梯度下降为什么会收敛",
            self_assessed_level="beginner",
        )
    )
    conversations = ConversationService(SqlConversationRepository(database))
    context_builder = ContextBuilder(
        memory=MemoryModule(memory_repository),
        conversations=conversations,
        summary_manager=ConversationSummaryManager(
            conversations,
            RuleBasedSummaryBackend(),
        ),
        traces=ContextTraceRepository(database),
    )
    client = RecordingRoleClient()
    retriever = FiveChunkRetriever()
    workflow = MaterialQaWorkflow(
        agent=MaterialQaAgent(client),
        retriever=retriever,
        qa_service=MaterialQaService(conversations=conversations),
        context_builder=context_builder,
    )
    conversation = workflow.create_conversation(book_id="ml", user_id="alice")
    for index in range(8):
        conversations.append(
            conversation.conversation_id,
            actor_user_id="alice",
            role="user" if index % 2 == 0 else "assistant",
            content=f"历史对话 {index}：" + "内容" * 40,
            request_id=f"seed-{index}",
        )

    question = "请结合资料和我的学习状态继续解释：" + "问题" * 400
    answer = workflow.ask(
        conversation_id=conversation.conversation_id,
        book_id="ml",
        question=question,
        actor_user_id="alice",
    )

    assert answer.refused is False
    assert len(retriever.history) == 8
    assert [message["role"] for message in client.messages] == ["system", "user"]
    payload = _payload(client.messages[1]["content"])
    assert set(payload["context"]) == {
        "current_input",
        "learner",
        "workflow",
        "conversation",
    }
    assert payload["context"]["current_input"] == question
    learner = payload["context"]["learner"]
    assert learner["preferences"]["content_style"] == "visual"
    assert learner["current_confusions"] == "梯度下降为什么会收敛"
    assert [
        item["knowledge_point_id"] for item in learner["verified_mastery"]
    ] == ["kp-0"]
    prompt_history = payload["context"]["conversation"]["recent_messages"]
    assert len(prompt_history) == 8
    assert all(set(message) == {"role", "content"} for message in prompt_history)
    visible_chunk_count = len(payload["external"]["retrieval_chunks"])
    assert 0 < visible_chunk_count < 5
    assert len(answer.citations) == visible_chunk_count
    assert "identity" not in payload["context"]
    assert "trace" not in payload["context"]
    assert "constraints" not in payload["context"]

    policy = ContextPolicyRegistry().get(ContextMode.TUTOR)
    rendered_size = sum(
        len(message["content"].encode("utf-8")) for message in client.messages
    )
    assert rendered_size <= (
        policy.max_context_tokens - policy.response_reserve_tokens
    )

    with database.session() as session:
        traces = list(
            session.execute(
                select(ContextTraceRow).where(
                    ContextTraceRow.conversation_id == conversation.conversation_id
                )
            ).scalars()
        )
    final_trace = next(
        trace for trace in traces if not trace.request_id.endswith(":retrieval")
    )
    assert final_trace.estimated_tokens == rendered_size
    assert final_trace.selected_message_range == {"from": 1, "to": 8}
    assert final_trace.policy_version == "context-policy-v2"
    database.close()
