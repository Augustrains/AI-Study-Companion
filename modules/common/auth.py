"""统一的当前用户边界。

本地演示可使用 ``X-User-Id``；关闭开发身份后，只接受经 HS256
签名验证的 Bearer JWT，业务模块始终只接收 ``CurrentUser``。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Header

from .errors import (
    AuthenticationRequiredError,
    ConfigurationError,
    PermissionDeniedError,
)


@dataclass(frozen=True)
class CurrentUser:
    user_id: str


class IdentityResolver:
    def __init__(
        self,
        *,
        allow_dev_identity: bool = True,
        dev_user_id: str = "user_001",
        jwt_secret: str | None = None,
    ) -> None:
        self.allow_dev_identity = allow_dev_identity
        self.dev_user_id = dev_user_id
        self.jwt_secret = str(jwt_secret or "")

    @staticmethod
    def _decode_segment(value: str) -> bytes:
        try:
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        except (ValueError, TypeError) as exc:
            raise AuthenticationRequiredError("invalid bearer token") from exc

    def _verified_subject(self, token: str) -> str:
        if not self.jwt_secret:
            raise ConfigurationError(
                "JWT verification secret is not configured",
                details={"variable": "STUDY_COMPANION_JWT_SECRET"},
            )
        try:
            encoded_header, encoded_payload, encoded_signature = token.split(".")
            header = json.loads(self._decode_segment(encoded_header))
            payload: Any = json.loads(self._decode_segment(encoded_payload))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AuthenticationRequiredError("invalid bearer token") from exc
        if not isinstance(header, dict) or not isinstance(payload, dict):
            raise AuthenticationRequiredError("invalid bearer token")
        if header.get("alg") != "HS256" or header.get("typ", "JWT") != "JWT":
            raise AuthenticationRequiredError("unsupported bearer token")
        signing_input = f"{encoded_header}.{encoded_payload}".encode()
        expected = hmac.new(
            self.jwt_secret.encode(), signing_input, hashlib.sha256
        ).digest()
        provided = self._decode_segment(encoded_signature)
        if not hmac.compare_digest(expected, provided):
            raise AuthenticationRequiredError("invalid bearer token signature")
        now = time.time()
        try:
            if "exp" not in payload or float(payload["exp"]) <= now:
                raise AuthenticationRequiredError("bearer token has expired")
            if "nbf" in payload and float(payload["nbf"]) > now:
                raise AuthenticationRequiredError("bearer token is not active")
        except (TypeError, ValueError) as exc:
            raise AuthenticationRequiredError("invalid bearer token claims") from exc
        subject = str(payload.get("sub", "")).strip()
        if not subject:
            raise AuthenticationRequiredError("bearer token subject is missing")
        return subject

    def __call__(
        self,
        authorization: str | None = Header(default=None, alias="Authorization"),
        x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    ) -> CurrentUser:
        scheme, _, credentials = str(authorization or "").partition(" ")
        if authorization:
            if scheme.lower() != "bearer" or not credentials.strip():
                raise AuthenticationRequiredError("Bearer token is required")
            return CurrentUser(user_id=self._verified_subject(credentials.strip()))

        if not self.allow_dev_identity:
            raise AuthenticationRequiredError(
                "Bearer token is required",
                details={"header": "Authorization"},
            )
        user_id = str(x_user_id or self.dev_user_id).strip()
        if not user_id:
            raise AuthenticationRequiredError("development user id is empty")
        return CurrentUser(user_id=user_id)

    @staticmethod
    def require_claimed_user(
        current_user: CurrentUser,
        claimed_user_id: str | None,
    ) -> str:
        claimed = str(claimed_user_id or "").strip()
        if claimed and claimed != current_user.user_id:
            raise PermissionDeniedError(
                "request user does not match the authenticated user",
                details={"field": "userId"},
            )
        return current_user.user_id
