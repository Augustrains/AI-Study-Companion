"""认证接口路由。

路径与前端 services/session.ts 的 authEndpoints 完全对应：
    POST   /api/auth/register
    POST   /api/auth/login
    POST   /api/auth/login-code
    POST   /api/auth/send-code
    POST   /api/auth/logout
    GET    /api/auth/me
    PATCH  /api/auth/profile
    PATCH  /api/auth/password

令牌通过 Authorization: Bearer <token> 传递。
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Response, status

from .errors import UnauthenticatedError
from .models import AuthAccount, AuthSession
from .module import AuthModule
from .schemas import (
    AuthSessionResponse,
    AuthUserResponse,
    LoginByCodeRequest,
    LoginRequest,
    RegisterRequest,
    SendCodeRequest,
    SendCodeResponse,
    UpdatePasswordRequest,
    UpdateProfileRequest,
)


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthenticatedError("请先登录。")
    return authorization[7:].strip()


def _user_response(account: AuthAccount) -> AuthUserResponse:
    return AuthUserResponse(**account.public_view())


def _session_response(session: AuthSession) -> AuthSessionResponse:
    return AuthSessionResponse(
        token=session.token,
        user=_user_response(session.account),
        expiresAt=session.expires_at,
    )


def build_router(module: AuthModule) -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.post("/api/auth/register", response_model=AuthSessionResponse)
    def register(payload: RegisterRequest) -> AuthSessionResponse:
        return _session_response(
            module.register(nickname=payload.nickname, account=payload.account, password=payload.password)
        )

    @router.post("/api/auth/login", response_model=AuthSessionResponse)
    def login(payload: LoginRequest) -> AuthSessionResponse:
        return _session_response(module.login(account=payload.account, password=payload.password))

    @router.post("/api/auth/login-code", response_model=AuthSessionResponse)
    def login_by_code(payload: LoginByCodeRequest) -> AuthSessionResponse:
        return _session_response(module.login_by_code(account=payload.account, code=payload.code))

    @router.post("/api/auth/send-code", response_model=SendCodeResponse)
    def send_code(payload: SendCodeRequest) -> SendCodeResponse:
        sent, dev_code = module.send_code(account=payload.account, scene=payload.scene)
        return SendCodeResponse(
            sent=sent,
            devCode=dev_code,
            delivery="console" if module.expose_code else "email_or_sms",
        )

    @router.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout() -> Response:
        """当前令牌是无状态签名令牌，服务端没有会话表可清；前端清除本地存储即可。

        换成服务端会话或加令牌黑名单后，这里再实现真正的撤销。
        """
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/api/auth/me", response_model=AuthUserResponse)
    def me(authorization: str | None = Header(default=None)) -> AuthUserResponse:
        return _user_response(module.current_account(_bearer(authorization)))

    @router.patch("/api/auth/profile", response_model=AuthUserResponse)
    def update_profile(
        payload: UpdateProfileRequest,
        authorization: str | None = Header(default=None),
    ) -> AuthUserResponse:
        account = module.update_profile(
            _bearer(authorization),
            nickname=payload.nickname,
            avatar_color=payload.avatar_color,
        )
        return _user_response(account)

    @router.patch("/api/auth/password", status_code=status.HTTP_204_NO_CONTENT)
    def update_password(
        payload: UpdatePasswordRequest,
        authorization: str | None = Header(default=None),
    ) -> Response:
        module.update_password(
            _bearer(authorization),
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return router
