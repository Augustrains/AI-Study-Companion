"""Message persistence for material question answering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping
from sqlalchemy.exc import SQLAlchemyError

from modules.common.errors import ResourceNotFoundError, StorageReadError, StorageWriteError, ValidationAppError

from .models import (
    AnswerMode,
    MaterialQaLearningTask,
    MaterialQaMessage,
    ResponseQuality,
    SocraticStateName,
)
from .schemas import MaterialQaSource

MessageRole = Literal["user", "assistant", "system"]


class MaterialQaMessageStore(Protocol):
    """Storage operations required by the material-QA workflow."""

    def list_recent(
        self,
        *,
        user_id: str,
        book_id: str,
        limit: int = 12,
    ) -> list[MaterialQaMessage]: ...

    def add_message(
        self,
        *,
        user_id: str,
        book_id: str,
        role: MessageRole,
        content: str,
        citations: list[MaterialQaSource] | None = None,
        answer_mode: AnswerMode = "direct",
        learning_task_id: str | None = None,
        socratic_state: SocraticStateName | None = None,
        response_quality: ResponseQuality | None = None,
        socratic_completed: bool = False,
    ) -> int: ...

    def save_exchange(
        self,
        *,
        user_id: str,
        book_id: str,
        question: str,
        answer: str,
        citations: list[MaterialQaSource] | None = None,
        answer_mode: AnswerMode = "direct",
        learning_task_id: str | None = None,
        socratic_state: SocraticStateName | None = None,
        response_quality: ResponseQuality | None = None,
        socratic_completed: bool = False,
    ) -> None: ...

    def reset_context(self, *, user_id: str, book_id: str) -> None: ...

    def get_learning_task(
        self, *, user_id: str, book_id: str, learning_task_id: str
    ) -> MaterialQaLearningTask | None: ...

    def get_active_learning_task(
        self, *, user_id: str, book_id: str
    ) -> MaterialQaLearningTask | None: ...

    def finish_learning_task(
        self, *, user_id: str, book_id: str, learning_task_id: str
    ) -> None: ...


@dataclass
class _MemoryMessage:
    id: int
    user_id: str
    book_id: str
    role: str
    content: str
    is_context_reset: bool
    created_at: str
    answer_mode: AnswerMode = "direct"
    learning_task_id: str | None = None
    socratic_state: SocraticStateName | None = None
    response_quality: ResponseQuality | None = None
    socratic_completed: bool = False

# 消息仓储的“内存版实现”
class InMemoryMaterialQaMessageStore:
    """In-memory adapter used by unit tests and dependency-free workflows."""

    def __init__(self) -> None:
        self.rows: list[_MemoryMessage] = []

    def list_recent(self, *, user_id: str, book_id: str, limit: int = 12) -> list[MaterialQaMessage]:
        reset_id = max(
            (
                row.id
                for row in self.rows
                if row.user_id == user_id and row.book_id == book_id and row.is_context_reset
            ),
            default=0,
        )
        rows = [
            row
            for row in self.rows
            if row.id > reset_id
            and row.user_id == user_id
            and row.book_id == book_id
            and not row.is_context_reset
            and row.role in ("user", "assistant")
        ][-limit:]
        return [
            MaterialQaMessage(
                role=row.role,  # type: ignore[arg-type]
                content=row.content,
                created_at=row.created_at,
                answer_mode=row.answer_mode,
                learning_task_id=row.learning_task_id,
                socratic_state=row.socratic_state,
                response_quality=row.response_quality,
                socratic_completed=row.socratic_completed,
            )
            for row in rows
        ]

    def add_message(
        self,
        *,
        user_id: str,
        book_id: str,
        role: MessageRole,
        content: str,
        citations: list[MaterialQaSource] | None = None,
        answer_mode: AnswerMode = "direct",
        learning_task_id: str | None = None,
        socratic_state: SocraticStateName | None = None,
        response_quality: ResponseQuality | None = None,
        socratic_completed: bool = False,
    ) -> int:
        del citations
        row_id = len(self.rows) + 1
        self.rows.append(
            _MemoryMessage(
                id=row_id,
                user_id=user_id,
                book_id=book_id,
                role=role,
                content=content,
                is_context_reset=False,
                created_at=datetime.now(timezone.utc).isoformat(),
                answer_mode=answer_mode,
                learning_task_id=learning_task_id,
                socratic_state=socratic_state,
                response_quality=response_quality,
                socratic_completed=socratic_completed,
            )
        )
        return row_id

    def reset_context(self, *, user_id: str, book_id: str) -> None:
        row_id = len(self.rows) + 1
        self.rows.append(
            _MemoryMessage(
                id=row_id,
                user_id=user_id,
                book_id=book_id,
                role="system",
                content="",
                is_context_reset=True,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        )

    def save_exchange(
        self,
        *,
        user_id: str,
        book_id: str,
        question: str,
        answer: str,
        citations: list[MaterialQaSource] | None = None,
        answer_mode: AnswerMode = "direct",
        learning_task_id: str | None = None,
        socratic_state: SocraticStateName | None = None,
        response_quality: ResponseQuality | None = None,
        socratic_completed: bool = False,
    ) -> None:
        self.add_message(
            user_id=user_id,
            book_id=book_id,
            role="user",
            content=question,
            answer_mode=answer_mode,
            learning_task_id=learning_task_id,
            response_quality=response_quality,
        )
        self.add_message(
            user_id=user_id,
            book_id=book_id,
            role="assistant",
            content=answer,
            citations=citations,
            answer_mode=answer_mode,
            learning_task_id=learning_task_id,
            socratic_state=socratic_state,
            socratic_completed=socratic_completed,
        )

    def _task_rows(self, *, user_id: str, book_id: str, learning_task_id: str) -> list[_MemoryMessage]:
        reset_id = max(
            (row.id for row in self.rows if row.user_id == user_id and row.book_id == book_id and row.is_context_reset),
            default=0,
        )
        return [
            row for row in self.rows
            if row.id > reset_id
            and row.user_id == user_id
            and row.book_id == book_id
            and row.learning_task_id == learning_task_id
            and not row.is_context_reset
        ]

    # 从数据库或内存中的多条消息记录里，重新组装出某一道苏格拉底学习任务的当前状态。
    # 比如用户最初问题 最新一轮模型回答 最新一轮教学状态，停留在该状态下的次数,当前任务ID
    def get_learning_task(
        self, *, user_id: str, book_id: str, learning_task_id: str
    ) -> MaterialQaLearningTask | None:
        rows = self._task_rows(user_id=user_id, book_id=book_id, learning_task_id=learning_task_id)
        user_rows = [row for row in rows if row.role == "user"]
        assistant_rows = [row for row in rows if row.role == "assistant"]
        if not user_rows or not assistant_rows:
            return None
        latest = assistant_rows[-1]
        state = latest.socratic_state or "probe"
        turns = 0
        for row in reversed(assistant_rows[:-1]):
            if row.socratic_state != state:
                break
            turns += 1
        return MaterialQaLearningTask(
            learning_task_id=learning_task_id,
            root_question=user_rows[0].content,
            state=state,
            turns_in_state=turns,
            completed=rows[-1].socratic_completed,
            last_assistant_message=latest.content,
        )

    def get_active_learning_task(self, *, user_id: str, book_id: str) -> MaterialQaLearningTask | None:
        for row in reversed(self.rows):
            if row.user_id == user_id and row.book_id == book_id and row.is_context_reset:
                return None
            if row.user_id == user_id and row.book_id == book_id and row.learning_task_id:
                task = self.get_learning_task(
                    user_id=user_id,
                    book_id=book_id,
                    learning_task_id=row.learning_task_id,
                )
                return task if task and not task.completed else None
        return None

    def finish_learning_task(self, *, user_id: str, book_id: str, learning_task_id: str) -> None:
        self.add_message(
            user_id=user_id,
            book_id=book_id,
            role="system",
            content="",
            answer_mode="socratic",
            learning_task_id=learning_task_id,
            socratic_completed=True,
        )

# 消息仓储的“mysql版实现”
class MysqlMaterialQaMessageStore:
    """Store one append-only message stream per database user and book."""

    BOOK_NAMES = {
        "ml": "ML-For-Beginners",
        "dl": "AI-For-Beginners",
    }

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._book_id_cache: dict[str, int] = {}

    @staticmethod
    def _numeric_user_id(user_id: str) -> int:
        try:
            return int(user_id)
        except (TypeError, ValueError) as exc:
            raise ValidationAppError(
                "material QA requires an authenticated database user",
                details={"user_id": user_id},
                cause=exc,
            ) from exc

    def _database_book_id(self, connection, book_id: str) -> int:
        cached = self._book_id_cache.get(book_id)
        if cached is not None:
            return cached

        try:
            numeric_id = int(book_id)
        except (TypeError, ValueError):
            numeric_id = 0

        if numeric_id:
            statement = text("SELECT id FROM books WHERE id = :book_id LIMIT 1")
            parameters = {"book_id": numeric_id}
        else:
            book_name = self.BOOK_NAMES.get(book_id)
            if book_name is None:
                raise ResourceNotFoundError("material QA book not found", details={"book_id": book_id})
            statement = text("SELECT id FROM books WHERE book_name = :book_name LIMIT 1")
            parameters = {"book_name": book_name}

        row = connection.execute(statement, parameters).mappings().first()
        if row is None:
            raise ResourceNotFoundError("material QA book not found", details={"book_id": book_id})
        result = int(row["id"])
        self._book_id_cache[book_id] = result
        return result

    @staticmethod
    def _to_message(row: RowMapping) -> MaterialQaMessage:
        created_at = row["created_at"]
        return MaterialQaMessage(
            role=str(row["role"]),  # type: ignore[arg-type]
            content=str(row["content"]),
            created_at=created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at),
            answer_mode=str(row["qa_mode"] or "direct"),  # type: ignore[arg-type]
            learning_task_id=str(row["learning_task_id"]) if row["learning_task_id"] else None,
            socratic_state=str(row["socratic_state"]) if row["socratic_state"] else None,  # type: ignore[arg-type]
            response_quality=str(row["response_quality"]) if row["response_quality"] else None,  # type: ignore[arg-type]
            socratic_completed=bool(row["socratic_completed"]),
        )

    def list_recent(self, *, user_id: str, book_id: str, limit: int = 12) -> list[MaterialQaMessage]:
        if limit <= 0:
            raise ValidationAppError("history limit must be positive", details={"limit": limit})
        statement = text(
            "SELECT role, content, created_at, qa_mode, learning_task_id, socratic_state, "
            "response_quality, socratic_completed FROM consultation_messages "
            "WHERE user_id = :user_id AND book_id = :book_id AND is_context_reset = 0 "
            "AND role IN ('user', 'assistant') "
            "AND id > COALESCE((SELECT MAX(reset_row.id) FROM consultation_messages AS reset_row "
            "WHERE reset_row.user_id = :user_id AND reset_row.book_id = :book_id "
            "AND reset_row.is_context_reset = 1), 0) "
            "ORDER BY id DESC LIMIT :limit"
        )
        try:
            with self.engine.connect() as connection:
                database_book_id = self._database_book_id(connection, book_id)
                rows = connection.execute(
                    statement,
                    {
                        "user_id": self._numeric_user_id(user_id),
                        "book_id": database_book_id,
                        "limit": limit,
                    },
                ).mappings().all()
        except ResourceNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise StorageReadError("failed to read material QA history", cause=exc) from exc
        return [self._to_message(row) for row in reversed(rows)]
    # 增加消息
    def add_message(
        self,
        *,
        user_id: str,
        book_id: str,
        role: MessageRole,
        content: str,
        citations: list[MaterialQaSource] | None = None,
        answer_mode: AnswerMode = "direct",
        learning_task_id: str | None = None,
        socratic_state: SocraticStateName | None = None,
        response_quality: ResponseQuality | None = None,
        socratic_completed: bool = False,
    ) -> int:
        statement = text(
            "INSERT INTO consultation_messages "
            "(user_id, book_id, role, content, `references`, created_at, is_context_reset, "
            "qa_mode, learning_task_id, socratic_state, response_quality, socratic_completed) "
            "VALUES (:user_id, :book_id, :role, :content, :references, :created_at, 0, "
            ":qa_mode, :learning_task_id, :socratic_state, :response_quality, :socratic_completed)"
        )
        references = json.dumps(
            [citation.model_dump(by_alias=True) for citation in citations or []],
            ensure_ascii=False,
        ) if citations else None
        try:
            with self.engine.begin() as connection:
                database_book_id = self._database_book_id(connection, book_id)
                result = connection.execute(
                    statement,
                    {
                        "user_id": self._numeric_user_id(user_id),
                        "book_id": database_book_id,
                        "role": role,
                        "content": content,
                        "references": references,
                        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
                        "qa_mode": answer_mode,
                        "learning_task_id": learning_task_id,
                        "socratic_state": socratic_state,
                        "response_quality": response_quality,
                        "socratic_completed": int(socratic_completed),
                    },
                )
            if result.lastrowid is None:
                raise StorageWriteError("MySQL did not return the material QA message ID")
            return int(result.lastrowid)
        except (ResourceNotFoundError, StorageWriteError):
            raise
        except SQLAlchemyError as exc:
            raise StorageWriteError("failed to save material QA message", cause=exc) from exc

    # 在这里执行重置
    def reset_context(self, *, user_id: str, book_id: str) -> None:
        statement = text(
            "INSERT INTO consultation_messages "
            "(user_id, book_id, role, content, `references`, created_at, is_context_reset) "
            "VALUES (:user_id, :book_id, 'system', '', NULL, :created_at, 1)"
        )
        try:
            with self.engine.begin() as connection:
                database_book_id = self._database_book_id(connection, book_id)
                connection.execute(
                    statement,
                    {
                        "user_id": self._numeric_user_id(user_id),
                        "book_id": database_book_id,
                        "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
                    },
                )
        except ResourceNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise StorageWriteError("failed to reset material QA context", cause=exc) from exc
    # 将一轮问答作为一个整体，安全地写入数据库，同时保存回答引用，保证在同一个事务当中
    def save_exchange(
        self,
        *,
        user_id: str,
        book_id: str,
        question: str,
        answer: str,
        citations: list[MaterialQaSource] | None = None,
        answer_mode: AnswerMode = "direct",
        learning_task_id: str | None = None,
        socratic_state: SocraticStateName | None = None,
        response_quality: ResponseQuality | None = None,
        socratic_completed: bool = False,
    ) -> None:
        statement = text(
            "INSERT INTO consultation_messages "
            "(user_id, book_id, role, content, `references`, created_at, is_context_reset, "
            "qa_mode, learning_task_id, socratic_state, response_quality, socratic_completed) "
            "VALUES (:user_id, :book_id, :role, :content, :references, :created_at, 0, "
            ":qa_mode, :learning_task_id, :socratic_state, :response_quality, :socratic_completed)"
        )
        references = json.dumps(
            [citation.model_dump(by_alias=True) for citation in citations or []],
            ensure_ascii=False,
        ) if citations else None
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            with self.engine.begin() as connection:
                database_book_id = self._database_book_id(connection, book_id)
                common = {
                    "user_id": self._numeric_user_id(user_id),
                    "book_id": database_book_id,
                    "created_at": now,
                    "qa_mode": answer_mode,
                    "learning_task_id": learning_task_id,
                }
                connection.execute(
                    statement,
                    {
                        **common,
                        "role": "user",
                        "content": question,
                        "references": None,
                        "socratic_state": None,
                        "response_quality": response_quality,
                        "socratic_completed": 0,
                    },
                )
                connection.execute(
                    statement,
                    {
                        **common,
                        "role": "assistant",
                        "content": answer,
                        "references": references,
                        "socratic_state": socratic_state,
                        "response_quality": None,
                        "socratic_completed": int(socratic_completed),
                    },
                )
        except ResourceNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise StorageWriteError("failed to save material QA exchange", cause=exc) from exc

    @staticmethod
    def _task_from_rows(
        rows: list[RowMapping], learning_task_id: str
    ) -> MaterialQaLearningTask | None:
        user_rows = [row for row in rows if str(row["role"]) == "user"]
        assistant_rows = [row for row in rows if str(row["role"]) == "assistant"]
        if not user_rows or not assistant_rows:
            return None
        latest = assistant_rows[-1]
        state = str(latest["socratic_state"] or "probe")
        turns = 0
        for row in reversed(assistant_rows[:-1]):
            if str(row["socratic_state"] or "probe") != state:
                break
            turns += 1
        return MaterialQaLearningTask(
            learning_task_id=learning_task_id,
            root_question=str(user_rows[0]["content"]),
            state=state,  # type: ignore[arg-type]
            turns_in_state=turns,
            completed=bool(rows[-1]["socratic_completed"]),
            last_assistant_message=str(latest["content"]),
        )

    def get_learning_task(
        self, *, user_id: str, book_id: str, learning_task_id: str
    ) -> MaterialQaLearningTask | None:
        statement = text(
            "SELECT role, content, socratic_state, socratic_completed "
            "FROM consultation_messages "
            "WHERE user_id = :user_id AND book_id = :book_id "
            "AND learning_task_id = :learning_task_id AND is_context_reset = 0 "
            "AND id > COALESCE((SELECT MAX(reset_row.id) FROM consultation_messages AS reset_row "
            "WHERE reset_row.user_id = :user_id AND reset_row.book_id = :book_id "
            "AND reset_row.is_context_reset = 1), 0) ORDER BY id"
        )
        try:
            with self.engine.connect() as connection:
                database_book_id = self._database_book_id(connection, book_id)
                rows = connection.execute(
                    statement,
                    {
                        "user_id": self._numeric_user_id(user_id),
                        "book_id": database_book_id,
                        "learning_task_id": learning_task_id,
                    },
                ).mappings().all()
        except ResourceNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise StorageReadError("failed to read Socratic learning task", cause=exc) from exc
        return self._task_from_rows(list(rows), learning_task_id)

    def get_active_learning_task(self, *, user_id: str, book_id: str) -> MaterialQaLearningTask | None:
        statement = text(
            "SELECT learning_task_id FROM consultation_messages "
            "WHERE user_id = :user_id AND book_id = :book_id AND is_context_reset = 0 "
            "AND qa_mode = 'socratic' AND learning_task_id IS NOT NULL "
            "AND id > COALESCE((SELECT MAX(reset_row.id) FROM consultation_messages AS reset_row "
            "WHERE reset_row.user_id = :user_id AND reset_row.book_id = :book_id "
            "AND reset_row.is_context_reset = 1), 0) ORDER BY id DESC LIMIT 1"
        )
        try:
            with self.engine.connect() as connection:
                database_book_id = self._database_book_id(connection, book_id)
                row = connection.execute(
                    statement,
                    {"user_id": self._numeric_user_id(user_id), "book_id": database_book_id},
                ).mappings().first()
        except ResourceNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise StorageReadError("failed to read active Socratic learning task", cause=exc) from exc
        if not row:
            return None
        task = self.get_learning_task(
            user_id=user_id,
            book_id=book_id,
            learning_task_id=str(row["learning_task_id"]),
        )
        return task if task and not task.completed else None

    def finish_learning_task(self, *, user_id: str, book_id: str, learning_task_id: str) -> None:
        self.add_message(
            user_id=user_id,
            book_id=book_id,
            role="system",
            content="",
            answer_mode="socratic",
            learning_task_id=learning_task_id,
            socratic_completed=True,
        )
