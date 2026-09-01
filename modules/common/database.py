"""数据库连接基础设施。

提供连接池和只读连通性检查，业务模块尚未接入。
"""

from __future__ import annotations

from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Engine

from .config import Settings
from .errors import ConfigurationError


def create_mysql_engine(settings: Settings) -> Engine:
    """根据配置创建 MySQL 连接池，不在日志或异常中暴露密码。"""

    required = {
        "STUDY_COMPANION_DB_HOST": settings.db_host,
        "STUDY_COMPANION_DB_NAME": settings.db_name,
        "STUDY_COMPANION_DB_USER": settings.db_user,
        "STUDY_COMPANION_DB_PASSWORD": settings.db_password,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ConfigurationError(
            "MySQL connection is not configured",
            details={"variables": missing},
        )

    url = URL.create(
        drivername="mysql+pymysql",
        username=settings.db_user,
        password=settings.db_password,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)


def check_mysql_connection(engine: Engine) -> None:
    """执行只读探针；成功返回，失败由 SQLAlchemy 原样抛出。"""

    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
