from typing import Protocol


class LLMClient(Protocol):
    """后续接入真实模型时遵循的最小接口。"""

    def generate(self, prompt: str) -> str:
        ...


class NullLLMClient:
    """Demo 默认实现，避免首次运行依赖模型服务。"""

    def generate(self, prompt: str) -> str:
        return ""
