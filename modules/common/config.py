"""应用配置与环境变量管理。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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
    backend_port: int = 8000
    # 前端开发服务器端口。
    frontend_port: int = 5173
    # 日志级别，例如 DEBUG、INFO、WARNING。
    log_level: str = "INFO"
    # 是否让前端调用真实后端 API。
    use_real_api: bool = True
    # 是否启用存储备份策略，供持久化层使用。
    storage_backup: bool = True

    @property
    def database_url(self) -> str:
        """业务数据库 URL；本地默认 SQLite，生产环境可直接使用 PostgreSQL。"""

        default_path = (self.data_dir / "study_companion.sqlite3").resolve()
        return os.getenv(
            "STUDY_COMPANION_DATABASE_URL",
            f"sqlite+pysqlite:///{default_path}",
        )

    @property
    def checkpoint_backend(self) -> str:
        backend = os.getenv("STUDY_COMPANION_CHECKPOINT_BACKEND", "sqlite").lower()
        if backend not in {"sqlite", "postgres"}:
            raise ConfigurationError(
                "STUDY_COMPANION_CHECKPOINT_BACKEND must be sqlite or postgres",
                details={"variable": "STUDY_COMPANION_CHECKPOINT_BACKEND"},
            )
        return backend

    @property
    def checkpoint_url(self) -> str:
        default_path = (self.data_dir / "langgraph_checkpoints.sqlite3").resolve()
        return os.getenv("STUDY_COMPANION_CHECKPOINT_URL", str(default_path))

    @property
    def profile_path(self) -> Path:
        """返回学习者档案 JSON 文件的默认路径。"""
        return self.data_dir / "profiles" / "learner_profiles.json"

    @property
    def memory_path(self) -> Path:
        """记忆模块持久化文件的默认路径。"""
        return self.data_dir / "memory" / "learner_memories.json"

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

    @classmethod
    def from_env(cls, project_dir: str | Path | None = None) -> "Settings":
        """从环境变量构造配置对象。

        ``project_dir`` 主要用于测试或嵌入式启动场景；未传入时自动按
        当前 common 包的位置推导项目根目录。
        """
        root = Path(project_dir or Path(__file__).resolve().parents[2]).resolve()
        data_dir = Path(os.getenv("STUDY_COMPANION_DATA_DIR", root / "data")).resolve()
        return cls(root, data_dir, os.getenv("STUDY_COMPANION_HOST", "127.0.0.1"), _int("STUDY_COMPANION_BACKEND_PORT", 8000), _int("STUDY_COMPANION_FRONTEND_PORT", 5173), os.getenv("STUDY_COMPANION_LOG_LEVEL", "INFO").upper(), _bool("STUDY_COMPANION_USE_REAL_API", True), _bool("STUDY_COMPANION_STORAGE_BACKUP", True))
