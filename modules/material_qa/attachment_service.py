"""Application service for material-QA attachment workflows."""

from __future__ import annotations

from pathlib import Path

from modules.common.errors import ValidationAppError

from .attachment_repository import MaterialQaAttachmentRepository
from .attachment_storage import AttachmentStorage
from .models import MaterialQaAttachment


class MaterialQaAttachmentService:
    """协调附件校验、公共读OSS上传和数据库元数据保存。"""

    IMAGE_MAX_BYTES = 10 * 1024 * 1024
    PDF_MAX_BYTES = 20 * 1024 * 1024

    ALLOWED_FILE_TYPES = {
        "image/jpeg": {".jpg", ".jpeg"},
        "image/png": {".png"},
        "image/webp": {".webp"},
        "application/pdf": {".pdf"},
    }

    # 注入对象存储和数据库仓库，使业务层统一协调两种持久化资源。
    def __init__(
        self,
        *,
        storage: AttachmentStorage,
        repository: MaterialQaAttachmentRepository,
    ) -> None:
        self.storage = storage
        self.repository = repository

    # 校验文件名、MIME类型、扩展名、空内容和文件大小，并返回安全文件名。
    @classmethod
    def _validate_file(cls, *, file_name: str, file_type: str, content: bytes) -> str:
        normalized_name = Path(file_name.strip()).name
        if not normalized_name or normalized_name in {".", ".."}:
            raise ValidationAppError("attachment file name is required")
        if file_type not in cls.ALLOWED_FILE_TYPES:
            raise ValidationAppError(
                "unsupported attachment file type",
                details={"file_type": file_type, "allowed": sorted(cls.ALLOWED_FILE_TYPES)},
            )
        suffix = Path(normalized_name).suffix.lower()
        if suffix not in cls.ALLOWED_FILE_TYPES[file_type]:
            raise ValidationAppError(
                "attachment extension does not match its file type",
                details={"file_name": normalized_name, "file_type": file_type},
            )
        if not content:
            raise ValidationAppError("attachment content cannot be empty")
        max_bytes = cls.PDF_MAX_BYTES if file_type == "application/pdf" else cls.IMAGE_MAX_BYTES
        if len(content) > max_bytes:
            raise ValidationAppError(
                "attachment is too large",
                details={"file_size": len(content), "max_bytes": max_bytes},
            )
        return normalized_name
    # 上传附件
    # 校验文件→上传OSS→获得公共URL→写入附件表→返回附件记录。
    # 先将文件上传到OSS，再写入附件表；数据库失败时清理已经上传的对象。
    def upload(
        self,
        *,
        user_id: str,
        message_id: int,
        file_name: str,
        file_type: str,
        content: bytes,
    ) -> MaterialQaAttachment:
        """Upload bytes first, then persist their stable public OSS URL."""

        normalized_name = self._validate_file(
            file_name=file_name,
            file_type=file_type,
            content=content,
        )
        file_url = self.storage.save(
            user_id=user_id,
            file_name=normalized_name,
            file_type=file_type,
            content=content,
        )
        try:
            return self.repository.create(
                user_id=user_id,
                message_id=message_id,
                file_name=normalized_name,
                file_type=file_type,
                file_size=len(content),
                file_url=file_url,
            )
        except Exception:
            # Avoid leaving an unreferenced object when metadata persistence fails.
            try:
                self.storage.delete(file_url=file_url)
            except Exception:
                pass
            raise

    # 查询当前用户某条问答消息下的附件列表。
    def list_for_message(self, *, user_id: str, message_id: int) -> list[MaterialQaAttachment]:
        return self.repository.list_by_message_id(user_id=user_id, message_id=message_id)
    # 删除附件
    # 先移除数据库记录，再删除已经不被业务引用的OSS对象。
    def delete(self, *, user_id: str, attachment_id: int) -> MaterialQaAttachment:
        """先删除元数据，再删除不再被引用的OSS对象。"""

        attachment = self.repository.delete(
            user_id=user_id,
            attachment_id=attachment_id,
        )
        self.storage.delete(file_url=attachment.file_url)
        return attachment
