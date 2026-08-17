"""LLM 客户端的最小抽象和 DeepSeek 实现。"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from dotenv import dotenv_values, load_dotenv

from modules.common.errors import ConfigurationError, ExternalServiceError

_PROJECT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def generate_messages_compat(
    client: object,
    messages: list[dict[str, str]],
) -> str:
    """Use role-aware generation when available and preserve simple test clients."""

    method = getattr(client, "generate_messages", None)
    if callable(method):
        return method(messages)
    prompt = "\n\n".join(
        f"[{message.get('role', 'user')}]\n{message.get('content', '')}"
        for message in messages
    )
    return client.generate(prompt)  # type: ignore[attr-defined]


class LLMClient(Protocol):
    """业务 Agent 依赖的最小文本生成接口。"""

    def generate(self, prompt: str) -> str: ...

    def generate_messages(self, messages: list[dict[str, str]]) -> str: ...


@dataclass(frozen=True)
class DeepSeekLLMClient:
    """通过 OpenAI-compatible Chat Completions API 生成文本。"""

    api_key: str | None = None
    model: str = "deepseek-v4-flash"
    base_url: str = "https://opencode.ai/zen/go/v1"
    timeout: float = 120.0

    @classmethod
    def from_env(cls) -> DeepSeekLLMClient:
        """从环境变量创建客户端，不在构造阶段发起网络请求。"""

        file_config = dotenv_values(_PROJECT_ENV_FILE)
        load_dotenv(_PROJECT_ENV_FILE, override=False)
        timeout_value = os.getenv("STUDY_COMPANION_LLM_TIMEOUT", "120")
        try:
            timeout = float(timeout_value)
        except ValueError as exc:
            raise ConfigurationError(
                "STUDY_COMPANION_LLM_TIMEOUT must be a number",
                details={"variable": "STUDY_COMPANION_LLM_TIMEOUT"},
                cause=exc,
            ) from exc
        if timeout <= 0:
            raise ConfigurationError(
                "STUDY_COMPANION_LLM_TIMEOUT must be positive",
                details={"variable": "STUDY_COMPANION_LLM_TIMEOUT"},
            )

        return cls(
            api_key=(
                os.getenv("STUDY_COMPANION_LLM_API_KEY")
                or file_config.get("STUDY_COMPANION_LLM_API_KEY")
                or file_config.get("DEEPSEEK_API_KEY")
                or os.getenv("DEEPSEEK_API_KEY")
            ),
            model=os.getenv("STUDY_COMPANION_LLM_MODEL", "deepseek-v4-flash"),
            base_url=os.getenv(
                "STUDY_COMPANION_LLM_BASE_URL", "https://opencode.ai/zen/go/v1"
            ),
            timeout=timeout,
        )

    def generate(self, prompt: str) -> str:
        """通过 OpenAI-compatible Chat Completions 接口生成回答。"""

        return self.generate_messages([{"role": "user", "content": prompt}])

    def generate_messages(self, messages: list[dict[str, str]]) -> str:
        """保留 system/user 边界调用 Chat Completions。"""

        if not self.api_key:
            raise ConfigurationError(
                "LLM API key is not configured",
                details={"variable": "STUDY_COMPANION_LLM_API_KEY"},
            )

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        try:
            with httpx.Client(
                timeout=self.timeout,
                trust_env=False,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": "StudyCompanion/1.0",
                },
            ) as client:
                response = client.post(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    json=payload,
                )
                response.raise_for_status()
                result: Any = response.json()
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                "LLM API request failed",
                details={
                    "provider": "opencode",
                    "status_code": exc.response.status_code,
                },
                cause=exc,
            ) from exc
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise ExternalServiceError(
                "LLM API is temporarily unavailable",
                details={"provider": "opencode"},
                cause=exc,
            ) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ExternalServiceError(
                "LLM API returned an invalid response",
                details={"provider": "opencode"},
                cause=exc,
            ) from exc

        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ExternalServiceError(
                "LLM API response does not contain generated text",
                details={"provider": "opencode"},
                cause=exc,
            ) from exc
        if not isinstance(content, str) or not content.strip():
            raise ExternalServiceError(
                "LLM API returned empty generated text",
                details={"provider": "opencode"},
            )
        return content.strip()


class NullLLMClient:
    """无需外部模型服务的空实现，供测试或显式降级场景使用。"""

    def generate(self, prompt: str) -> str:
        del prompt
        return ""

    def generate_messages(self, messages: list[dict[str, str]]) -> str:
        del messages
        return ""
