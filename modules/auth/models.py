"""认证模块的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AuthAccount:
    """一个账号。password_hash / password_salt 之外不存任何凭据原文。"""

    user_id: str
    nickname: str
    account: str
    password_hash: str
    password_salt: str
    created_at: str
    # 迭代次数随账号存储：以后调高强度时，老账号仍能用原参数校验通过。
    iterations: int = 200_000
    avatar_color: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "nickname": self.nickname,
            "account": self.account,
            "password_hash": self.password_hash,
            "password_salt": self.password_salt,
            "created_at": self.created_at,
            "iterations": self.iterations,
            "avatar_color": self.avatar_color,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AuthAccount":
        return cls(
            user_id=str(payload["user_id"]),
            nickname=str(payload.get("nickname", "")),
            account=str(payload["account"]),
            password_hash=str(payload.get("password_hash", "")),
            password_salt=str(payload.get("password_salt", "")),
            created_at=str(payload.get("created_at", "")),
            iterations=int(payload.get("iterations", 200_000)),
            avatar_color=str(payload.get("avatar_color", "")),
        )

    def public_view(self) -> dict[str, Any]:
        """返回给前端的用户对象，字段名与 services/session.ts 的 AuthUser 对齐。"""
        return {
            "userId": self.user_id,
            "nickname": self.nickname,
            "account": self.account,
            "createdAt": self.created_at,
            "avatarColor": self.avatar_color,
        }


@dataclass(frozen=True)
class AuthSession:
    """一次登录的结果。"""

    token: str
    account: AuthAccount
    expires_at: str

    def to_dict(self) -> dict[str, Any]:
        return {"token": self.token, "user": self.account.public_view(), "expiresAt": self.expires_at}


@dataclass
class VerificationCode:
    """一次验证码申请。仅存在于进程内存，重启即失效。"""

    account: str
    code: str
    scene: str
    expires_at: datetime
    attempts: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
