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


class LLMClient(Protocol):
    """业务 Agent 依赖的最小文本生成接口。"""

    def generate(self, prompt: str) -> str:
        ...

    # 在一次请求中同时提交文字提示和公开可访问的图片URL。
    def generate_multimodal(self, prompt: str, *, image_urls: list[str]) -> str:
        ...


@dataclass(frozen=True)
class DeepSeekLLMClient:
    """通过 OpenAI-compatible Chat Completions API 生成文本。"""

    api_key: str | None = None
    model: str = "deepseek-v4-flash"
    base_url: str = "https://opencode.ai/zen/go/v1"
    timeout: float = 120.0

    @classmethod
    def from_env(cls) -> "DeepSeekLLMClient":
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
            base_url=os.getenv("STUDY_COMPANION_LLM_BASE_URL", "https://opencode.ai/zen/go/v1"),
            timeout=timeout,
        )

    def generate(self, prompt: str) -> str:
        """通过 OpenAI-compatible Chat Completions 接口生成回答。"""

        return self._generate_from_content(prompt)

    # 将文字和图片URL组成同一条user消息，只调用一次多模态模型。
    def generate_multimodal(self, prompt: str, *, image_urls: list[str]) -> str:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        content.extend(
            {"type": "image_url", "image_url": {"url": image_url}}
            for image_url in image_urls
        )
        return self._generate_from_content(content)

    def generate_json(self, prompt: str, *, image_urls: list[str] | None = None) -> str:
        """Request one JSON object from providers supporting the OpenAI schema.

        This is deliberately opt-in: several existing agents request prose, so
        forcing JSON at the shared ``generate`` boundary would break them.
        """

        content: str | list[dict[str, Any]] = prompt
        if image_urls:
            content = [{"type": "text", "text": prompt}]
            content.extend(
                {"type": "image_url", "image_url": {"url": image_url}}
                for image_url in image_urls
            )
        return self._generate_from_content(content, response_format={"type": "json_object"})

    # 统一发送纯文本或多模态Chat Completions请求并解析返回文本。
    def _generate_from_content(
        self,
        content: str | list[dict[str, Any]],
        *,
        response_format: dict[str, str] | None = None,
    ) -> str:

        if not self.api_key:
            raise ConfigurationError(
                "LLM API key is not configured",
                details={"variable": "STUDY_COMPANION_LLM_API_KEY"},
            )

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
        }
        if response_format is not None:
            payload["response_format"] = response_format
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
                details={"provider": "opencode", "status_code": exc.response.status_code},
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

    # 空客户端不访问图片，只保持与真实多模态客户端一致的接口。
    def generate_multimodal(self, prompt: str, *, image_urls: list[str]) -> str:
        del prompt, image_urls
        return ""
