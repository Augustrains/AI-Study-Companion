"""应用层共享异常定义。

异常由 common 或业务模块抛出，由 API 层转换为前端响应，同时由日志层记录。
本文件不负责写日志，也不直接依赖 FastAPI。
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """所有应用异常的基类，携带稳定错误码和结构化上下文。"""

    code = "APP_ERROR"
    status_code = 500
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        cause: Exception | None = None,
    ) -> None:
        """创建异常。

        Args:
            message: 面向开发者或用户的错误描述。
            details: 与错误相关的结构化字段，例如字段名或资源 ID。
            cause: 导致当前异常的底层原始异常，仅建议用于日志排查。
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.cause = cause


class ValidationAppError(AppError):
    """请求参数或输入数据不符合要求。"""

    code = "VALIDATION_ERROR"
    status_code = 400


class RequestValidationAppError(AppError):
    """HTTP 请求未通过 Pydantic 接口契约校验。"""

    code = "REQUEST_VALIDATION_ERROR"
    status_code = 422


class ResourceNotFoundError(AppError):
    """请求的资源不存在，例如题库或诊断会话。"""

    code = "RESOURCE_NOT_FOUND"
    status_code = 404


class StorageReadError(AppError):
    """读取本地或其他持久化资源时发生错误。"""

    code = "STORAGE_READ_ERROR"
    status_code = 500


class StorageWriteError(AppError):
    """写入本地或其他持久化资源时发生错误。"""

    code = "STORAGE_WRITE_ERROR"
    status_code = 500


class WorkflowStateError(AppError):
    """当前工作流状态不允许执行请求的操作。"""

    code = "WORKFLOW_STATE_ERROR"
    status_code = 409


class ExternalServiceError(AppError):
    """调用外部服务失败，通常允许上层进行重试。"""

    code = "EXTERNAL_SERVICE_ERROR"
    status_code = 502
    retryable = True


class SerializationAppError(AppError):
    """领域对象与外部数据转换失败。"""

    code = "SERIALIZATION_ERROR"
    status_code = 400


class ConflictError(AppError):
    """请求与当前资源状态发生冲突。"""

    code = "CONFLICT"
    status_code = 409


class PermissionDeniedError(AppError):
    """当前调用方无权执行目标操作。"""

    code = "PERMISSION_DENIED"
    status_code = 403


class AuthenticationRequiredError(AppError):
    """请求缺少可信的调用方身份。"""

    code = "AUTHENTICATION_REQUIRED"
    status_code = 401


class ConfigurationError(AppError):
    """应用配置缺失、类型错误或取值不合法。"""

    code = "CONFIGURATION_ERROR"
    status_code = 500
