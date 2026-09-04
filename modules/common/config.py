"""应用配置与环境变量管理。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .errors import ConfigurationError


def _bool(name: str, default: bool) -> bool:
    """读取布尔型环境变量，支持 true/false、1/0、yes/no。"""
    value = os.getenv(name)
    if value is None:
        return default
    if value.lower() not in {"true", "false", "1", "0", "yes", "no"}:
        raise ConfigurationError(f"{name} must be a boolean", details={"variable": name})
    return value.lower() in {"true", "1", "yes"}


def _int(name: str, default: int) -> int:
    """读取正整数环境变量，并在配置非法时抛出统一异常。"""
    value = os.getenv(name)
    if value is None:
        return default
    try:
        result = int(value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer", details={"variable": name}, cause=exc) from exc
    if result <= 0:
        raise ConfigurationError(f"{name} must be positive", details={"variable": name})
    return result


@dataclass(frozen=True)
class Settings:
    """应用运行时配置。

    配置优先从 ``STUDY_COMPANION_*`` 环境变量读取；启动参数可以在
    应用入口处覆盖 host、端口等运行参数。对象不可变，避免运行过程中
    被业务代码意外修改。
    """

    # 项目根目录，用于定位默认资源和相对路径。
    project_dir: Path
    # 数据根目录，默认是项目根目录下的 data/。
    data_dir: Path
    # 后端 API 监听地址。
    host: str = "127.0.0.1"
    # 后端 API 监听端口。
    backend_port: int = 8001
    # 前端开发服务器端口。
    frontend_port: int = 5173
    # 日志级别，例如 DEBUG、INFO、WARNING。
    log_level: str = "INFO"
    # 是否让前端调用真实后端 API。
    use_real_api: bool = True
    # 是否启用存储备份策略，供持久化层使用。
    storage_backup: bool = True
    # MySQL 连接配置；第一阶段只负责读取，不在此处建立连接。
    db_host: str = ""
    db_port: int = 3306
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""

    @property
    def question_new_dir(self) -> Path:
        return self.data_dir / "question_new"

    @property
    def knowledge_points_dir(self) -> Path:
        return self.question_new_dir / "知识点"

    @property
    def new_material_dir(self) -> Path:
        return self.question_new_dir / "教材"

    @property
    def qdrant_path(self) -> Path:
        """本地 Qdrant 持久化目录，可通过环境变量覆盖。"""
        # BGE-M3 生成 1024 维向量，不能复用旧中文模型的 512 维索引。
        default_path = self.data_dir / "qdrant-bge-m3"
        return Path(os.getenv("STUDY_COMPANION_QDRANT_PATH", default_path)).resolve()

    @property
    def embedding_model(self) -> str:
        """资料问答使用的 Embedding 模型名称或本地路径。"""
        default_model = self.project_dir / "models" / "bge-m3"
        return os.getenv("STUDY_COMPANION_EMBEDDING_MODEL", str(default_model) if default_model.exists() else "BAAI/bge-m3")

    @property
    def tavily_api_key(self) -> str | None:
        """Optional Tavily MCP credential for the daily material-search agent."""
        return os.getenv("TAVILY_API_KEY") or None

    @classmethod
    def from_env(cls, project_dir: str | Path | None = None) -> "Settings":
        """从环境变量构造配置对象。

        ``project_dir`` 主要用于测试或嵌入式启动场景；未传入时自动按
        当前 common 包的位置推导项目根目录。
        """
        root = Path(project_dir or Path(__file__).resolve().parents[2]).resolve()
        load_dotenv(root / ".env", override=False)
        data_dir = Path(os.getenv("STUDY_COMPANION_DATA_DIR", root / "data")).resolve()
        return cls(root, data_dir, os.getenv("STUDY_COMPANION_HOST", "127.0.0.1"), _int("STUDY_COMPANION_BACKEND_PORT", 8001), _int("STUDY_COMPANION_FRONTEND_PORT", 5173), os.getenv("STUDY_COMPANION_LOG_LEVEL", "INFO").upper(), _bool("STUDY_COMPANION_USE_REAL_API", True), _bool("STUDY_COMPANION_STORAGE_BACKUP", True))
        # 允许从项目根目录 .env 读取配置；显式系统环境变量优先。
        load_dotenv(root / ".env", override=False)
        data_dir = Path(os.getenv("STUDY_COMPANION_DATA_DIR", root / "data")).resolve()
        return cls(
            root,
            data_dir,
            os.getenv("STUDY_COMPANION_HOST", "127.0.0.1"),
            _int("STUDY_COMPANION_BACKEND_PORT", 8000),
            _int("STUDY_COMPANION_FRONTEND_PORT", 5173),
            os.getenv("STUDY_COMPANION_LOG_LEVEL", "INFO").upper(),
            _bool("STUDY_COMPANION_USE_REAL_API", True),
            _bool("STUDY_COMPANION_STORAGE_BACKUP", True),
            os.getenv("STUDY_COMPANION_DB_HOST", ""),
            _int("STUDY_COMPANION_DB_PORT", 3306),
            os.getenv("STUDY_COMPANION_DB_NAME", ""),
            os.getenv("STUDY_COMPANION_DB_USER", ""),
            os.getenv("STUDY_COMPANION_DB_PASSWORD", ""),
        )
