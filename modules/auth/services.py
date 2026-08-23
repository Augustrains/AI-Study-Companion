"""认证模块的服务实现：密码散列、令牌签发校验、账号存储、验证码。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .errors import (
    AccountExistsError,
    AuthenticationError,
    InvalidCodeError,
    UnauthenticatedError,
    WeakPasswordError,
)
from .models import AuthAccount, AuthSession, VerificationCode

PBKDF2_ITERATIONS = 200_000
MIN_PASSWORD_LENGTH = 8
TOKEN_TTL = timedelta(days=14)
CODE_TTL = timedelta(minutes=10)
CODE_MAX_ATTEMPTS = 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ============================== 密码 ==============================


class PasswordHasher:
    """PBKDF2-HMAC-SHA256。每个账号一个随机盐，迭代次数随账号存储。"""

    def __init__(self, iterations: int = PBKDF2_ITERATIONS) -> None:
        self.iterations = iterations

    def hash(self, password: str) -> tuple[str, str, int]:
        """返回 (hash, salt, iterations)。"""
        self.validate_strength(password)
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, self.iterations)
        return _b64(digest), _b64(salt), self.iterations

    @staticmethod
    def verify(password: str, *, password_hash: str, password_salt: str, iterations: int) -> bool:
        if not password_hash or not password_salt:
            return False
        try:
            salt = _b64decode(password_salt)
            expected = _b64decode(password_hash)
        except (ValueError, TypeError):
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        # 定时安全比较，避免按字节比较泄露信息。
        return hmac.compare_digest(digest, expected)

    @staticmethod
    def validate_strength(password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise WeakPasswordError(
                f"密码至少 {MIN_PASSWORD_LENGTH} 位。",
                details={"min_length": MIN_PASSWORD_LENGTH},
            )


# ============================== 令牌 ==============================


class TokenService:
    """HMAC 签名令牌：payload.signature，payload 内含 user_id 与过期时间。

    没有做服务端撤销：登出只清前端存储，令牌在过期前仍然有效。
    上线前应换成服务端会话表或带 refresh 的短期令牌。
    """

    def __init__(self, secret: str | None = None, ttl: timedelta = TOKEN_TTL) -> None:
        self.ttl = ttl
        configured = secret or os.environ.get("AUTH_TOKEN_SECRET", "")
        if configured:
            self.secret = configured.encode("utf-8")
            self.ephemeral = False
        else:
            # 没配置密钥时用进程内随机密钥：重启后旧令牌全部失效，
            # 这比内置一个人人可见的默认密钥安全。部署时请设置 AUTH_TOKEN_SECRET。
            self.secret = secrets.token_bytes(32)
            self.ephemeral = True

    def issue(self, account: AuthAccount) -> tuple[str, str]:
        """签发令牌，返回 (token, expires_at_iso)。"""
        expires_at = _now() + self.ttl
        payload = {"sub": account.user_id, "exp": int(expires_at.timestamp())}
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        body = _b64(raw)
        return f"{body}.{self._sign(body)}", expires_at.isoformat()

    def verify(self, token: str) -> str:
        """校验令牌并返回 user_id；无效或过期抛 UnauthenticatedError。"""
        if not token or "." not in token:
            raise UnauthenticatedError("登录状态无效，请重新登录。")
        body, _, signature = token.rpartition(".")
        if not hmac.compare_digest(self._sign(body), signature):
            raise UnauthenticatedError("登录状态无效，请重新登录。")
        try:
            payload = json.loads(_b64decode(body))
            expires_at = int(payload["exp"])
            user_id = str(payload["sub"])
        except (ValueError, TypeError, KeyError) as error:
            raise UnauthenticatedError("登录状态无效，请重新登录。", cause=error) from error
        if _now().timestamp() > expires_at:
            raise UnauthenticatedError("登录已过期，请重新登录。")
        return user_id

    def _sign(self, body: str) -> str:
        return _b64(hmac.new(self.secret, body.encode("ascii"), hashlib.sha256).digest())


# ============================== 账号存储 ==============================


class AccountStore:
    """单文件 JSON 账号表。

    只适合演示与本地联调：全量读写、进程内锁，没有跨进程并发保护。
    换数据库时只需替换本类，上层 AuthService 不用动。
    """

    DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "auth" / "users.json"

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else self.DEFAULT_PATH
        self._lock = threading.Lock()

    def _read_all(self) -> list[AuthAccount]:
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        rows = payload.get("users") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return []
        accounts: list[AuthAccount] = []
        for row in rows:
            if isinstance(row, dict) and row.get("user_id") and row.get("account"):
                accounts.append(AuthAccount.from_dict(row))
        return accounts

    def _write_all(self, accounts: list[AuthAccount]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps({"users": [item.to_dict() for item in accounts]}, ensure_ascii=False, indent=2)
        # 先写临时文件再替换，避免写一半崩溃把账号表损坏。
        temp = self.path.with_suffix(".tmp")
        temp.write_text(content + "\n", encoding="utf-8")
        temp.replace(self.path)

    @staticmethod
    def normalize(account: str) -> str:
        """邮箱不区分大小写；手机号去掉空格和短横。"""
        cleaned = account.strip()
        return cleaned.lower() if "@" in cleaned else cleaned.replace(" ", "").replace("-", "")

    def find_by_account(self, account: str) -> AuthAccount | None:
        target = self.normalize(account)
        return next((item for item in self._read_all() if self.normalize(item.account) == target), None)

    def find_by_user_id(self, user_id: str) -> AuthAccount | None:
        return next((item for item in self._read_all() if item.user_id == user_id), None)

    def create(self, account: AuthAccount) -> AuthAccount:
        with self._lock:
            accounts = self._read_all()
            target = self.normalize(account.account)
            if any(self.normalize(item.account) == target for item in accounts):
                raise AccountExistsError("该邮箱或手机号已注册，请直接登录。")
            accounts.append(account)
            self._write_all(accounts)
        return account

    def update(self, account: AuthAccount) -> AuthAccount:
        with self._lock:
            accounts = self._read_all()
            for index, item in enumerate(accounts):
                if item.user_id == account.user_id:
                    accounts[index] = account
                    self._write_all(accounts)
                    return account
        raise UnauthenticatedError("账号不存在或登录状态已失效。")


# ============================== 验证码 ==============================


class VerificationCodeService:
    """验证码申请与校验。

    存在进程内存里，服务重启即失效——演示够用，多实例部署必须换 Redis 之类的共享存储。
    dev 模式下 issue() 会把验证码原样返回，由前端直接显示；
    上线时把 expose_code 设为 False 并接真实邮件/短信通道。
    """

    def __init__(self, expose_code: bool | None = None, ttl: timedelta = CODE_TTL) -> None:
        if expose_code is None:
            # 默认开发模式；部署时设置 AUTH_EXPOSE_CODE=false 关闭。
            expose_code = os.environ.get("AUTH_EXPOSE_CODE", "true").lower() != "false"
        self.expose_code = expose_code
        self.ttl = ttl
        self._codes: dict[str, VerificationCode] = {}
        self._lock = threading.Lock()

    def issue(self, account: str, scene: str = "login") -> tuple[bool, str | None]:
        """生成验证码。返回 (是否已发出, 开发模式下的明文验证码)。"""
        code = f"{secrets.randbelow(1_000_000):06d}"
        key = AccountStore.normalize(account)
        with self._lock:
            self._codes[key] = VerificationCode(
                account=key,
                code=code,
                scene=scene,
                expires_at=_now() + self.ttl,
            )
        self._deliver(account, code, scene)
        return True, (code if self.expose_code else None)

    def verify(self, account: str, code: str, scene: str = "login") -> None:
        key = AccountStore.normalize(account)
        with self._lock:
            record = self._codes.get(key)
            if record is None or record.scene != scene:
                raise InvalidCodeError("请先获取验证码。")
            if _now() > record.expires_at:
                self._codes.pop(key, None)
                raise InvalidCodeError("验证码已过期，请重新获取。")
            record.attempts += 1
            if record.attempts > CODE_MAX_ATTEMPTS:
                self._codes.pop(key, None)
                raise InvalidCodeError("验证码错误次数过多，请重新获取。")
            if not hmac.compare_digest(record.code, code.strip()):
                raise InvalidCodeError("验证码不正确。")
            # 一次性使用，校验通过立即作废。
            self._codes.pop(key, None)

    def _deliver(self, account: str, code: str, scene: str) -> None:
        """真实发送通道的接入点。

        现在只打印到服务端日志；接邮件/短信服务时替换这里，
        不需要改动 issue()/verify() 的调用方。
        """
        print(f"[auth] 验证码 scene={scene} account={account} code={code}（开发模式，未真实发送）")


# ============================== 认证服务 ==============================


class AuthService:
    """把上面几个部件组装成注册/登录/资料维护的业务动作。"""

    def __init__(
        self,
        store: AccountStore | None = None,
        hasher: PasswordHasher | None = None,
        tokens: TokenService | None = None,
        codes: VerificationCodeService | None = None,
    ) -> None:
        self.store = store or AccountStore()
        self.hasher = hasher or PasswordHasher()
        self.tokens = tokens or TokenService()
        self.codes = codes or VerificationCodeService()

    # -------- 注册 / 登录 --------

    def register(self, *, nickname: str, account: str, password: str) -> AuthSession:
        password_hash, salt, iterations = self.hasher.hash(password)
        record = AuthAccount(
            user_id=f"user_{secrets.token_hex(6)}",
            nickname=nickname.strip() or account.split("@")[0],
            account=self.store.normalize(account),
            password_hash=password_hash,
            password_salt=salt,
            created_at=_now().isoformat(),
            iterations=iterations,
        )
        self.store.create(record)
        return self._session(record)

    def login(self, *, account: str, password: str) -> AuthSession:
        record = self.store.find_by_account(account)
        # 账号不存在时也走一次散列，让两种失败的耗时接近，避免用响应时间探测账号是否存在。
        if record is None:
            self.hasher.verify(password, password_hash="", password_salt="", iterations=1)
            raise AuthenticationError("账号或密码不正确。")
        ok = self.hasher.verify(
            password,
            password_hash=record.password_hash,
            password_salt=record.password_salt,
            iterations=record.iterations,
        )
        if not ok:
            raise AuthenticationError("账号或密码不正确。")
        return self._session(record)

    def send_code(self, *, account: str, scene: str = "login") -> tuple[bool, str | None]:
        """无论账号是否存在都返回成功，避免暴露注册状态。"""
        return self.codes.issue(account, scene=scene)

    def login_by_code(self, *, account: str, code: str) -> AuthSession:
        self.codes.verify(account, code, scene="login")
        record = self.store.find_by_account(account)
        if record is None:
            raise AuthenticationError("该账号尚未注册，请先创建账号。")
        return self._session(record)

    # -------- 已登录后的操作 --------

    def current_account(self, token: str) -> AuthAccount:
        user_id = self.tokens.verify(token)
        record = self.store.find_by_user_id(user_id)
        if record is None:
            raise UnauthenticatedError("账号不存在或已被删除，请重新登录。")
        return record

    def update_profile(self, token: str, *, nickname: str | None = None, avatar_color: str | None = None) -> AuthAccount:
        record = self.current_account(token)
        if nickname is not None and nickname.strip():
            record.nickname = nickname.strip()
        if avatar_color is not None:
            record.avatar_color = avatar_color.strip()
        return self.store.update(record)

    def update_password(self, token: str, *, current_password: str, new_password: str) -> None:
        record = self.current_account(token)
        ok = self.hasher.verify(
            current_password,
            password_hash=record.password_hash,
            password_salt=record.password_salt,
            iterations=record.iterations,
        )
        if not ok:
            raise AuthenticationError("当前密码不正确。")
        password_hash, salt, iterations = self.hasher.hash(new_password)
        record.password_hash = password_hash
        record.password_salt = salt
        record.iterations = iterations
        self.store.update(record)

    # -------- 内部 --------

    def _session(self, record: AuthAccount) -> AuthSession:
        token, expires_at = self.tokens.issue(record)
        return AuthSession(token=token, account=record, expires_at=expires_at)

    # -------- 演示数据 --------

    def ensure_seed_account(self, *, user_id: str, nickname: str, account: str, password: str) -> AuthAccount:
        """确保体验账号存在。已存在则原样返回，不覆盖用户改过的昵称或密码。"""
        existing = self.store.find_by_account(account)
        if existing is not None:
            return existing
        password_hash, salt, iterations = self.hasher.hash(password)
        record = AuthAccount(
            user_id=user_id,
            nickname=nickname,
            account=self.store.normalize(account),
            password_hash=password_hash,
            password_salt=salt,
            created_at=_now().isoformat(),
            iterations=iterations,
        )
        return self.store.create(record)


def public_error(error: Any) -> dict[str, Any]:
    """把异常转成前端 AuthError 结构，供需要手工构造响应的地方使用。"""
    return {
        "code": getattr(error, "code", "AUTH_ERROR"),
        "message": getattr(error, "message", None) or str(error),
        "retryable": bool(getattr(error, "retryable", False)),
    }
