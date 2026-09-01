"""认证模块对外门面。api 层只依赖本类。"""

from __future__ import annotations

from pathlib import Path

from .models import AuthAccount, AuthSession
from .services import AccountStore, AuthService, PasswordHasher, TokenService, VerificationCodeService

# 体验账号。user_id 与 scripts/seed_demo_data.py 写入的演示数据保持一致，
# 登录后能直接看到诊断记录、掌握度、学习计划和到期复习项。
DEMO_ACCOUNT = {
    "user_id": "demo_user",
    "nickname": "体验账号",
    "account": "demo@study.local",
    "password": "demo1234",
}


class AuthModule:
    def __init__(
        self,
        store_path: str | Path | None = None,
        *,
        store: AccountStore | None = None,
        token_secret: str | None = None,
        expose_code: bool | None = None,
        seed_demo_account: bool = True,
    ) -> None:
        self.service = AuthService(
            store=store or AccountStore(store_path),
            hasher=PasswordHasher(),
            tokens=TokenService(token_secret),
            codes=VerificationCodeService(expose_code),
        )
        if seed_demo_account:
            self.service.ensure_seed_account(**DEMO_ACCOUNT)

    # 注册 / 登录
    def register(self, *, nickname: str, account: str, password: str) -> AuthSession:
        return self.service.register(nickname=nickname, account=account, password=password)

    def login(self, *, account: str, password: str) -> AuthSession:
        return self.service.login(account=account, password=password)

    def login_by_code(self, *, account: str, code: str) -> AuthSession:
        return self.service.login_by_code(account=account, code=code)

    def send_code(self, *, account: str, scene: str = "login") -> tuple[bool, str | None]:
        return self.service.send_code(account=account, scene=scene)

    # 已登录
    def current_account(self, token: str) -> AuthAccount:
        return self.service.current_account(token)

    def update_profile(self, token: str, *, nickname: str | None, avatar_color: str | None) -> AuthAccount:
        return self.service.update_profile(token, nickname=nickname, avatar_color=avatar_color)

    def update_password(self, token: str, *, current_password: str, new_password: str) -> None:
        self.service.update_password(token, current_password=current_password, new_password=new_password)

    @property
    def expose_code(self) -> bool:
        return self.service.codes.expose_code
