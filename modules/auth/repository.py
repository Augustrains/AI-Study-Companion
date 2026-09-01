"""数据访问层 认证账号的 MySQL 数据库/外部数据访问
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping
from sqlalchemy.exc import IntegrityError

from .errors import AccountExistsError, UnauthenticatedError
from .models import AuthAccount
from .services import AccountStore


class MysqlAccountStore:
    """读取既有 ``users`` 表中的账号记录。"""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    normalize = staticmethod(AccountStore.normalize)

    @staticmethod
    def _pack_password(account: AuthAccount) -> str:
        """把 PBKDF2 参数组合进 users.password_hash 单列。"""

        return "$".join(
            (
                "pbkdf2_sha256",
                str(account.iterations),
                account.password_salt,
                account.password_hash,
            )
        )

    @staticmethod
    def _unpack_password(stored_password: str) -> tuple[str, str, int]:
        """解析单列 PBKDF2 格式：算法$次数$盐值$摘要。"""

        try:
            algorithm, iterations_text, salt, password_hash = stored_password.split("$", 3)
            iterations = int(iterations_text)
        except (AttributeError, TypeError, ValueError) as exc:
            raise UnauthenticatedError("账号密码记录无效，请联系管理员。", cause=exc) from exc
        if algorithm != "pbkdf2_sha256" or not salt or not password_hash or iterations <= 0:
            raise UnauthenticatedError("账号密码记录无效，请联系管理员。")
        return password_hash, salt, iterations

    @staticmethod
    def _created_at(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()

    # 把数据库查询出来的一行 row，转换成 AuthAccount 对象。
    @classmethod
    def _to_account(cls, row: RowMapping) -> AuthAccount:
        password_hash, password_salt, iterations = cls._unpack_password(str(row["password_hash"]))
        return AuthAccount(
            user_id=str(row["user_id"]),
            nickname=str(row["nickname"] or row["username"]),
            account=str(row["username"]),
            password_hash=password_hash,
            password_salt=password_salt,
            iterations=iterations,
            avatar_color=str(row["avatar"] or ""),
            created_at=cls._created_at(row["created_at"]),
        )

    def find_by_account(self, account: str) -> AuthAccount | None:
        """按项目的 account 值查询 users.username；此方法只执行 SELECT。"""

        statement = text(
            "SELECT user_id, username, nickname, password_hash, avatar, created_at "
            "FROM users WHERE username = :username LIMIT 1"
        )
        with self.engine.connect() as connection:
            row = connection.execute(
                statement,
                {"username": self.normalize(account)},
            ).mappings().first()
        return self._to_account(row) if row is not None else None

    def find_by_user_id(self, user_id: str) -> AuthAccount | None:
        """按数据库的 BIGINT user_id 查询账号；此方法只执行 SELECT。"""

        try:
            numeric_id = int(user_id)
        except (TypeError, ValueError):
            return None

        statement = text(
            "SELECT user_id, username, nickname, password_hash, avatar, created_at "
            "FROM users WHERE user_id = :user_id LIMIT 1"
        )
        with self.engine.connect() as connection:
            row = connection.execute(
                statement,
                {"user_id": numeric_id},
            ).mappings().first()
        return self._to_account(row) if row is not None else None

    def create(self, account: AuthAccount) -> AuthAccount:
        """创建账号"""

        account.account = self.normalize(account.account)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        statement = text(
            "INSERT INTO users "
            "(username, nickname, password_hash, email, avatar, role, created_at, updated_at) "
            "VALUES (:username, :nickname, :password_hash, :email, :avatar, 0, :created_at, :updated_at)"
        )
        values = {
            "username": account.account,
            "nickname": account.nickname,
            "password_hash": self._pack_password(account),
            "email": account.account if "@" in account.account else None,
            "avatar": account.avatar_color,
            "created_at": now,
            "updated_at": now,
        }
        try:
            with self.engine.begin() as connection:
                result = connection.execute(statement, values)
            if result.lastrowid is None:
                raise RuntimeError("MySQL did not return the generated user ID")
            account.user_id = str(result.lastrowid)
            account.created_at = self._created_at(now)
            return account
        except IntegrityError as exc:
            if self.find_by_account(account.account) is not None:
                raise AccountExistsError("该邮箱或手机号已注册，请直接登录。") from exc
            raise

    def update(self, account: AuthAccount) -> AuthAccount:
        """持久化昵称、头像和密码变化；登录账号 username 不在此处修改。"""

        try:
            user_id = int(account.user_id)
        except (TypeError, ValueError) as exc:
            raise UnauthenticatedError("账号不存在或登录状态已失效。", cause=exc) from exc

        statement = text(
            "UPDATE users SET nickname = :nickname, avatar = :avatar, "
            "password_hash = :password_hash, updated_at = :updated_at "
            "WHERE user_id = :user_id"
        )
        values = {
            "user_id": user_id,
            "nickname": account.nickname,
            "avatar": account.avatar_color,
            "password_hash": self._pack_password(account),
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
        }
        with self.engine.begin() as connection:
            result = connection.execute(statement, values)
        if result.rowcount != 1:
            raise UnauthenticatedError("账号不存在或登录状态已失效。")
        return account
