"""资料问答附件的阿里云OSS存储边界。"""
# Bucket采用“公共读、后端写”：上传完成后直接返回公共URL。
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Protocol
from urllib.parse import quote, unquote, urlparse
from uuid import uuid4

from modules.common.config import Settings
from modules.common.errors import ConfigurationError, StorageWriteError, ValidationAppError

# AttachmentStorage 接口，定义统一的附件存储能力
class AttachmentStorage(Protocol):
    """Storage operations required by attachment upload and display flows."""

    def save(
        self,
        *,
        user_id: str,
        file_name: str,
        file_type: str,
        content: bytes,
    ) -> str: ...

    def delete(self, *, file_url: str) -> None: ...

# 阿里云 OSS 的具体实现
class OssAttachmentStorage:
    """将附件写入公共读Bucket，并返回稳定的公共URL。"""

    def __init__(self, *, bucket: Any, prefix: str = "material-qa", public_base_url: str = "") -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/") or "material-qa"
        self.public_base_url = public_base_url.rstrip("/")
    # 从环境变量创建 OSS 客户端
    @classmethod
    def from_settings(cls, settings: Settings) -> "OssAttachmentStorage":
        required = {
            "STUDY_COMPANION_OSS_ENDPOINT": settings.oss_endpoint,
            "STUDY_COMPANION_OSS_REGION": settings.oss_region,
            "STUDY_COMPANION_OSS_BUCKET": settings.oss_bucket,
            "OSS_ACCESS_KEY_ID": settings.oss_access_key_id,
            "OSS_ACCESS_KEY_SECRET": settings.oss_access_key_secret,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ConfigurationError(
                "Alibaba Cloud OSS is not configured",
                details={"variables": missing},
            )
        if not settings.oss_endpoint.startswith("https://"):
            raise ConfigurationError(
                "STUDY_COMPANION_OSS_ENDPOINT must use HTTPS",
                details={"variable": "STUDY_COMPANION_OSS_ENDPOINT"},
            )

        try:
            import oss2
        except ImportError as exc:
            raise ConfigurationError(
                "Alibaba Cloud OSS SDK is not installed",
                details={"package": "oss2"},
                cause=exc,
            ) from exc

        auth = oss2.ProviderAuthV4(
            oss2.credentials.EnvironmentVariableCredentialsProvider()
        )
        bucket = oss2.Bucket(
            auth,
            settings.oss_endpoint,
            settings.oss_bucket,
            region=settings.oss_region,
        )
        parsed = urlparse(settings.oss_endpoint)
        bucket_host = parsed.netloc
        if not bucket_host.startswith(f"{settings.oss_bucket}."):
            bucket_host = f"{settings.oss_bucket}.{bucket_host}"
        return cls(
            bucket=bucket,
            prefix=settings.oss_prefix,
            public_base_url=f"{parsed.scheme}://{bucket_host}",
        )
    # 校验用户 ID
    @staticmethod
    def _safe_user_segment(user_id: str) -> str:
        value = str(user_id).strip()
        if not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValidationAppError(
                "invalid attachment user ID",
                details={"user_id": user_id},
            )
        return value
    # 生成OSS内部唯一对象名称，防止同名文件互相覆盖。
    def _build_object_name(self, *, user_id: str, file_name: str) -> str:
        suffix = Path(file_name).suffix.lower()
        if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
            suffix = ".bin"
        now = datetime.now(timezone.utc)
        return (
            f"{self.prefix}/{self._safe_user_segment(user_id)}/"
            f"{now:%Y/%m}/{uuid4().hex}{suffix}"
        )
    # 上传附件并直接返回可公开读取的完整URL。
    def save(
        self,
        *,
        user_id: str,
        file_name: str,
        file_type: str,
        content: bytes,
    ) -> str:
        if not content:
            raise ValidationAppError("attachment content cannot be empty")
        object_name = self._build_object_name(user_id=user_id, file_name=file_name)
        try:
            self.bucket.put_object(
                object_name,
                content,
                headers={"Content-Type": file_type},
            )
        except Exception as exc:  # SDK exceptions vary by transport and version.
            raise StorageWriteError("failed to upload attachment to OSS", cause=exc) from exc
        if not self.public_base_url:
            raise ConfigurationError("OSS public base URL is not configured")
        return f"{self.public_base_url}/{quote(object_name, safe='/')}"

    # 从数据库公共URL中恢复删除接口需要的OSS对象名称。
    def _object_name_from_url(self, file_url: str) -> str:
        expected = f"{self.public_base_url}/"
        if not self.public_base_url or not file_url.startswith(expected):
            raise ValidationAppError("invalid OSS attachment public URL")
        return unquote(file_url[len(expected):])
    # 删除 OSS 文件
    def delete(self, *, file_url: str) -> None:
        try:
            self.bucket.delete_object(self._object_name_from_url(file_url))
        except Exception as exc:
            raise StorageWriteError("failed to delete attachment from OSS", cause=exc) from exc
