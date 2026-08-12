from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from modules.common import api as common_api

from .models import LongTermMemory


class JsonMemoryRepository:
    DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "memory" / "long_term_memories.json"

    def __init__(
        self,
        path: str | Path | None = None,
        reader: common_api.json_storage.JsonContentReader | None = None,
        store: common_api.json_storage.JsonStore | None = None,
    ) -> None:
        self.path = Path(path) if path is not None else Path(reader.path) if reader is not None else self.DEFAULT_PATH
        self.reader = reader or common_api.json_storage.JsonContentReader(self.path)
        self.store = store or common_api.json_storage.JsonStore()

    def upsert(self, memory: LongTermMemory) -> LongTermMemory:
        self.store.save(
            path=self.path,
            content=memory.to_dict(),
            mode="upsert",
            key_path=[memory.id],
        )
        return memory

    def remove(self, memory_id: str) -> None:
        records = self._read_all()
        if memory_id in records:
            records.pop(memory_id)
            self.store.save(path=self.path, content=records, mode="overwrite")

    def list_for_user(self, user_id: str, learning_domain: str | None = None) -> list[LongTermMemory]:
        records = self._read_all().values()
        return [
            common_api.serialization.from_data(LongTermMemory, item)
            for item in records
            if item.get("user_id") == user_id
            and (learning_domain is None or item.get("learning_domain") == learning_domain)
        ]

    def _read_all(self) -> dict[str, dict[str, Any]]:
        payload = self.reader.read(allow_missing=True, allow_empty=False)
        if not isinstance(payload, dict):
            raise common_api.errors.StorageReadError("memory resource must be a JSON object")
        return payload

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()
