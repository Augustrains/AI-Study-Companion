"""资料问答附件元数据的持久化边界。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping
from sqlalchemy.exc import SQLAlchemyError

from modules.common.errors import ResourceNotFoundError, StorageReadError, StorageWriteError
from .models import MaterialQaAttachment


class MaterialQaAttachmentRepository(Protocol):
    """附件业务层所需的数据库操作。"""

    # 创建附件元数据，并确保目标消息属于当前用户。
    def create(self, *, user_id: str, message_id: int, file_name: str,
               file_type: str, file_size: int, file_url: str) -> MaterialQaAttachment: ...

    # 按附件ID读取当前用户有权访问的附件。
    def get_by_id(self, *, user_id: str, attachment_id: int) -> MaterialQaAttachment | None: ...

    # 查询当前用户指定消息下的全部附件。
    def list_by_message_id(self, *, user_id: str, message_id: int) -> list[MaterialQaAttachment]: ...

    # 删除附件元数据，并返回原记录供上层清理OSS对象。
    def delete(self, *, user_id: str, attachment_id: int) -> MaterialQaAttachment: ...


# 将数据库日期时间转换成领域模型使用的ISO字符串。
def _timestamp(value: object) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


# 将SQLAlchemy查询结果转换成附件领域模型。
def _to_attachment(row: RowMapping) -> MaterialQaAttachment:
    return MaterialQaAttachment(
        id=int(row["id"]), message_id=int(row["message_id"]),
        file_name=str(row["file_name"]), file_type=str(row["file_type"]),
        file_size=int(row["file_size"]), file_url=str(row["file_url"]),
        created_at=_timestamp(row["created_at"]), updated_at=_timestamp(row["updated_at"]),
    )


class InMemoryMaterialQaAttachmentRepository:
    """供单元测试和无数据库流程使用的内存实现。"""

    # 初始化用户与附件记录的内存集合。
    def __init__(self) -> None:
        self.rows: list[tuple[str, MaterialQaAttachment]] = []

    # 在内存中创建一条附件元数据。
    def create(self, *, user_id: str, message_id: int, file_name: str,
               file_type: str, file_size: int, file_url: str) -> MaterialQaAttachment:
        now = datetime.now(timezone.utc).isoformat()
        attachment = MaterialQaAttachment(
            id=len(self.rows) + 1, message_id=message_id, file_name=file_name,
            file_type=file_type, file_size=file_size, file_url=file_url,
            created_at=now, updated_at=now,
        )
        self.rows.append((str(user_id), attachment))
        return attachment

    # 按附件ID查询当前用户自己的附件。
    def get_by_id(self, *, user_id: str, attachment_id: int) -> MaterialQaAttachment | None:
        return next((row for owner, row in self.rows
                     if owner == str(user_id) and row.id == attachment_id), None)

    # 查询当前用户指定消息下挂载的全部附件。
    def list_by_message_id(self, *, user_id: str, message_id: int) -> list[MaterialQaAttachment]:
        return [row for owner, row in self.rows
                if owner == str(user_id) and row.message_id == message_id]

    # 删除当前用户的附件元数据。
    def delete(self, *, user_id: str, attachment_id: int) -> MaterialQaAttachment:
        current = self.get_by_id(user_id=user_id, attachment_id=attachment_id)
        if current is None:
            raise ResourceNotFoundError("material QA attachment not found")
        self.rows = [(owner, row) for owner, row in self.rows
                     if not (owner == str(user_id) and row.id == attachment_id)]
        return current


class MysqlMaterialQaAttachmentRepository:
    """在MySQL中保存附件元数据，并通过消息归属限制访问。"""

    _SELECT_COLUMNS = (
        "a.id, a.message_id, a.file_name, a.file_type, a.file_size, "
        "a.file_url, a.created_at, a.updated_at"
    )

    # 注入项目共用的SQLAlchemy数据库连接池。
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # 将接口中的字符串用户ID转换成数据库整数ID。
    @staticmethod
    def _numeric_user_id(user_id: str) -> int:
        try:
            return int(user_id)
        except (TypeError, ValueError) as exc:
            raise ResourceNotFoundError("material QA attachment owner not found") from exc

    # 为属于当前用户的问答消息创建附件记录。
    def create(self, *, user_id: str, message_id: int, file_name: str,
               file_type: str, file_size: int, file_url: str) -> MaterialQaAttachment:
        statement = text(
            "INSERT INTO consultation_message_attachments "
            "(message_id, file_name, file_type, file_size, file_url) "
            "SELECT m.id, :file_name, :file_type, :file_size, :file_url "
            "FROM consultation_messages AS m "
            "WHERE m.id = :message_id AND m.user_id = :user_id"
        )
        try:
            with self.engine.begin() as connection:
                result = connection.execute(statement, {
                    "user_id": self._numeric_user_id(user_id), "message_id": message_id,
                    "file_name": file_name, "file_type": file_type,
                    "file_size": file_size, "file_url": file_url,
                })
                if result.rowcount != 1 or result.lastrowid is None:
                    raise ResourceNotFoundError("material QA message not found")
                attachment_id = int(result.lastrowid)
        except ResourceNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise StorageWriteError("failed to save material QA attachment metadata", cause=exc) from exc
        attachment = self.get_by_id(user_id=user_id, attachment_id=attachment_id)
        if attachment is None:
            raise StorageReadError("saved material QA attachment could not be read")
        return attachment

    # 通过附件ID查询附件，并验证消息所属用户。
    def get_by_id(self, *, user_id: str, attachment_id: int) -> MaterialQaAttachment | None:
        statement = text(
            f"SELECT {self._SELECT_COLUMNS} FROM consultation_message_attachments AS a "
            "JOIN consultation_messages AS m ON m.id = a.message_id "
            "WHERE a.id = :attachment_id AND m.user_id = :user_id LIMIT 1"
        )
        try:
            with self.engine.connect() as connection:
                row = connection.execute(statement, {
                    "attachment_id": attachment_id, "user_id": self._numeric_user_id(user_id),
                }).mappings().first()
        except SQLAlchemyError as exc:
            raise StorageReadError("failed to read material QA attachment", cause=exc) from exc
        return _to_attachment(row) if row is not None else None

    # 查询消息附件列表，并验证消息属于当前用户。
    def list_by_message_id(self, *, user_id: str, message_id: int) -> list[MaterialQaAttachment]:
        statement = text(
            f"SELECT {self._SELECT_COLUMNS} FROM consultation_message_attachments AS a "
            "JOIN consultation_messages AS m ON m.id = a.message_id "
            "WHERE a.message_id = :message_id AND m.user_id = :user_id ORDER BY a.id"
        )
        try:
            with self.engine.connect() as connection:
                rows = connection.execute(statement, {
                    "message_id": message_id, "user_id": self._numeric_user_id(user_id),
                }).mappings().all()
        except SQLAlchemyError as exc:
            raise StorageReadError("failed to list material QA attachments", cause=exc) from exc
        return [_to_attachment(row) for row in rows]

    # 删除附件记录，并返回原记录供业务层删除OSS对象。
    def delete(self, *, user_id: str, attachment_id: int) -> MaterialQaAttachment:
        current = self.get_by_id(user_id=user_id, attachment_id=attachment_id)
        if current is None:
            raise ResourceNotFoundError("material QA attachment not found")
        statement = text(
            "DELETE a FROM consultation_message_attachments AS a "
            "JOIN consultation_messages AS m ON m.id = a.message_id "
            "WHERE a.id = :attachment_id AND m.user_id = :user_id"
        )
        try:
            with self.engine.begin() as connection:
                result = connection.execute(statement, {
                    "attachment_id": attachment_id, "user_id": self._numeric_user_id(user_id),
                })
                if result.rowcount != 1:
                    raise ResourceNotFoundError("material QA attachment not found")
        except ResourceNotFoundError:
            raise
        except SQLAlchemyError as exc:
            raise StorageWriteError("failed to delete material QA attachment metadata", cause=exc) from exc
        return current
