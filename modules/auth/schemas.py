"""认证接口的请求/响应模型。

字段别名与前端 services/session.ts 一一对应，后端返回 camelCase。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AuthUserResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    user_id: str = Field(alias="userId")
    nickname: str
    account: str
    created_at: str = Field(alias="createdAt")
    avatar_color: str = Field(default="", alias="avatarColor")


class AuthSessionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    token: str
    user: AuthUserResponse
    expires_at: str = Field(alias="expiresAt")


class RegisterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nickname: str = Field(default="", max_length=40)
    account: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class LoginByCodeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=12)


class SendCodeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    account: str = Field(min_length=1, max_length=120)
    scene: str = Field(default="login", max_length=32)


class SendCodeResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    sent: bool = True
    # 开发模式下把验证码直接回给前端显示；
    # 设置环境变量 AUTH_EXPOSE_CODE=false 后该字段恒为 null，改由邮件/短信通道送达。
    dev_code: str | None = Field(default=None, alias="devCode")
    # 提示前端当前是「屏幕直显」还是「已发送到邮箱/手机」。
    delivery: str = "console"


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    nickname: str | None = Field(default=None, max_length=40)
    avatar_color: str | None = Field(default=None, alias="avatarColor", max_length=32)


class UpdatePasswordRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    current_password: str = Field(alias="currentPassword", min_length=1, max_length=200)
    new_password: str = Field(alias="newPassword", min_length=1, max_length=200)
