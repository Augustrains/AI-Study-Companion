from pathlib import Path

import pytest

from modules.common.errors import ValidationAppError
from modules.material_qa.services import QdrantMaterialIndexer, QdrantMaterialRetriever


def test_extract_original_material_excludes_learning_scaffolding() -> None:
    text = """---
content_unit_id: ml-unit-001
---

# 单元标题

## 学习目标

不应进入向量库。

## 原文学习材料

# Original chapter

Only this content should be indexed.
"""

    result = QdrantMaterialIndexer._extract_original_material(
        text,
        source_path=Path("ml-unit-001.md"),
    )

    assert result == "# Original chapter\n\nOnly this content should be indexed."
    assert "学习目标" not in result
    assert "原文学习材料" not in result


def test_extract_original_material_requires_section() -> None:
    with pytest.raises(ValidationAppError):
        QdrantMaterialIndexer._extract_original_material(
            "# Unit without the required section",
            source_path=Path("invalid.md"),
        )


class FakePoint:
    def __init__(self, version: int | None) -> None:
        self.payload = {"metadata": {"index_schema_version": version}}


class FakeClient:
    def __init__(self, version: int | None) -> None:
        self.version = version

    def collection_exists(self, _collection_name: str) -> bool:
        return True

    def scroll(self, **_kwargs):
        return [FakePoint(self.version)], None


def test_old_collection_requires_rebuild() -> None:
    indexer = QdrantMaterialIndexer(qdrant_path=Path("qdrant"), embedding_model="test")

    assert indexer.collection_needs_rebuild(
        client=FakeClient(version=None),
        collection_name="study_companion_ml",
    )
    assert not indexer.collection_needs_rebuild(
        client=FakeClient(version=indexer.INDEX_SCHEMA_VERSION),
        collection_name="study_companion_ml",
    )


def test_retriever_start_only_preloads_resources(monkeypatch) -> None:
    retriever = QdrantMaterialRetriever(
        documents={},
        qdrant_path=Path("qdrant"),
        embedding_model="test",
    )
    calls = []

    monkeypatch.setattr(retriever, "_resources", lambda: calls.append("resources"))
    monkeypatch.setattr(
        retriever.indexer,
        "build",
        lambda **_kwargs: pytest.fail("startup must not rebuild the index"),
    )

    retriever.start()

    assert calls == ["resources"]
