from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver

from modules.common.errors import ConfigurationError


@dataclass
class CheckpointResource:
    """Own one synchronous LangGraph saver and its connection lifecycle."""

    saver: Any
    _stack: ExitStack

    @classmethod
    def open(cls, *, backend: str, url: str) -> CheckpointResource:
        stack = ExitStack()
        try:
            if backend == "sqlite":
                path = Path(url).expanduser().resolve()
                path.parent.mkdir(parents=True, exist_ok=True)
                manager = SqliteSaver.from_conn_string(str(path))
            elif backend == "postgres":
                manager = PostgresSaver.from_conn_string(url)
            else:
                raise ConfigurationError(
                    "unsupported checkpoint backend",
                    details={"backend": backend},
                )
            saver = stack.enter_context(manager)
            saver.setup()
            return cls(saver=saver, _stack=stack)
        except BaseException:
            stack.close()
            raise

    def close(self) -> None:
        self._stack.close()
