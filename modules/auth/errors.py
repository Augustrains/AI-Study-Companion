"""认证模块的业务异常。

注意 status_code 的选择：前端 services/session.ts 把 404 / 405 / 501 当作
「后端没实现这个接口」并自动降级到本地会话。所以认证失败**绝不能**返回 404，
否则用户会在后端明确拒绝的情况下拿到一个本地伪造的登录态。
"""

from __future__ import annotations

from modules.common.errors import AppError


class AuthenticationError(AppError):
    """账号或密码/验证码不正确。

    刻意不区分「账号不存在」和「密码错误」，避免账号枚举。
    """

    code = "INVALID_CREDENTIALS"
    status_code = 401


class UnauthenticatedError(AppError):
    """缺少令牌、令牌无效或已过期。"""

    code = "UNAUTHENTICATED"
    status_code = 401


class AccountExistsError(AppError):
    """注册时账号已被占用。"""

    code = "ACCOUNT_EXISTS"
    status_code = 409


class InvalidCodeError(AppError):
    """验证码错误、过期或未申请。"""

    code = "INVALID_CODE"
    status_code = 400


class WeakPasswordError(AppError):
    """密码不满足最低强度要求。"""

    code = "WEAK_PASSWORD"
    status_code = 400
