"""Shared knowledge-point catalog loading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import StorageReadError, ValidationAppError
from .json_storage import JsonContentReader


@dataclass(frozen=True)
class KnowledgePoint:
    id: str
    name: str
    description: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "name": self.name, "description": self.description}


class JsonKnowledgePointCatalog:
    DOMAIN_FILES = {
        "machine_learning": "机器学习知识点.json",
        "deep_learning": "深度学习与AI知识点.json",
    }

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def list(self, learning_domain: str) -> list[KnowledgePoint]:
        filename = self.DOMAIN_FILES.get(learning_domain)
        if not filename:
            raise ValidationAppError(f"unsupported learning domain: {learning_domain}", details={"field": "learning_domain"})
        path = self.root / filename
        content = JsonContentReader(path).read()
        if not isinstance(content, dict) or not isinstance(content.get("knowledge_points"), list):
            raise StorageReadError(f"knowledge-point resource is invalid: {path}")
        return [
            KnowledgePoint(str(item["knowledge_point_id"]), str(item.get("name", "")), str(item.get("description", "")))
            for item in content["knowledge_points"]
            if isinstance(item, dict) and item.get("knowledge_point_id")
        ]

    def ids(self, learning_domain: str) -> list[str]:
        return [point.id for point in self.list(learning_domain)]

    def as_dicts(self, learning_domain: str) -> list[dict[str, str]]:
        return [point.to_dict() for point in self.list(learning_domain)]
