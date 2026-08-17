from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from modules.common import api as common_api

from .models import LearnerMemory


class MemoryRepository(Protocol):
    def get(self, user_id: str, learning_domain: str) -> LearnerMemory | None: ...

    def upsert(self, memory: LearnerMemory) -> LearnerMemory: ...

    def list_for_user(
        self,
        user_id: str,
        learning_domain: str | None = None,
    ) -> list[LearnerMemory]: ...

    @staticmethod
    def now() -> str: ...


class JsonMemoryRepository:
    DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "memory" / "learner_memories.json"

    def __init__(self, path: str | Path | None = None, reader: common_api.json_storage.JsonContentReader | None = None, store: common_api.json_storage.JsonStore | None = None) -> None:
        self.path = Path(path) if path is not None else Path(reader.path) if reader is not None else self.DEFAULT_PATH
        self.reader = reader or common_api.json_storage.JsonContentReader(self.path)
        self.store = store or common_api.json_storage.JsonStore()

    @staticmethod
    def key(user_id: str, learning_domain: str) -> str:
        return f"{user_id}:{learning_domain}"

    def get(self, user_id: str, learning_domain: str) -> LearnerMemory | None:
        payload = self._read_all().get(self.key(user_id, learning_domain))
        if not isinstance(payload, dict):
            return None
        return common_api.serialization.from_data(LearnerMemory, payload)

    def upsert(self, memory: LearnerMemory) -> LearnerMemory:
        self.store.save(path=self.path, content=memory.to_dict(), mode="upsert", key_path=[self.key(memory.user_id, memory.learning_domain)])
        return memory

    def list_for_user(self, user_id: str, learning_domain: str | None = None) -> list[LearnerMemory]:
        memories = []
        for payload in self._read_all().values():
            if not isinstance(payload, dict) or payload.get("user_id") != user_id:
                continue
            if learning_domain is not None and payload.get("learning_domain") != learning_domain:
                continue
            memories.append(common_api.serialization.from_data(LearnerMemory, payload))
        return memories

    def _read_all(self) -> dict[str, dict[str, Any]]:
        payload = self.reader.read(allow_missing=True, allow_empty=False)
        if not isinstance(payload, dict):
            raise common_api.errors.StorageReadError("learner memory resource must be a JSON object")
        return payload

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()
