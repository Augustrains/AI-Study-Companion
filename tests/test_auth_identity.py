import base64
import hashlib
import hmac
import json
import time

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from modules.common.auth import CurrentUser, IdentityResolver
from modules.common.errors import AppError, PermissionDeniedError

SECRET = "test-secret-that-is-long-enough"


def _segment(value: dict) -> str:
    data = json.dumps(value, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def token_for(subject: str, *, secret: str = SECRET, expires_in: int = 300) -> str:
    header = _segment({"alg": "HS256", "typ": "JWT"})
    payload = _segment({"sub": subject, "exp": int(time.time()) + expires_in})
    signature = hmac.new(
        secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256
    ).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{header}.{payload}.{encoded_signature}"


def identity_app() -> FastAPI:
    app = FastAPI()
    resolver = IdentityResolver(allow_dev_identity=False, jwt_secret=SECRET)
    current_user_dependency = Depends(resolver)

    @app.exception_handler(AppError)
    async def handle_app_error(_request, error: AppError):
        return JSONResponse(
            status_code=error.status_code,
            content={"code": error.code, "message": error.message},
        )

    @app.get("/me")
    def me(current_user: CurrentUser = current_user_dependency):
        return {"userId": current_user.user_id}

    return app


def test_identity_resolver_verifies_bearer_and_ignores_forgeable_user_header() -> None:
    client = TestClient(identity_app())

    assert client.get(
        "/me", headers={"Authorization": f"Bearer {token_for('alice')}"}
    ).json() == {
        "userId": "alice"
    }
    response = client.get("/me", headers={"X-User-Id": "alice"})
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_identity_resolver_rejects_expired_or_forged_bearer() -> None:
    client = TestClient(identity_app())

    expired = client.get(
        "/me", headers={"Authorization": f"Bearer {token_for('alice', expires_in=-1)}"}
    )
    forged = client.get(
        "/me",
        headers={
            "Authorization": f"Bearer {token_for('alice', secret='wrong-secret')}"
        },
    )
    assert expired.status_code == 401
    assert forged.status_code == 401


def test_development_identity_allows_explicit_header_or_default() -> None:
    resolver = IdentityResolver(allow_dev_identity=True, dev_user_id="user_001")

    assert resolver(authorization=None, x_user_id="alice").user_id == "alice"
    assert resolver(authorization=None, x_user_id=None).user_id == "user_001"


def test_claimed_user_cannot_override_authenticated_user() -> None:
    resolver = IdentityResolver()
    current = CurrentUser("alice")

    assert resolver.require_claimed_user(current, None) == "alice"
    assert resolver.require_claimed_user(current, "alice") == "alice"
    try:
        resolver.require_claimed_user(current, "bob")
    except PermissionDeniedError as error:
        assert error.status_code == 403
    else:  # pragma: no cover
        raise AssertionError("mismatched claimed user must be rejected")
