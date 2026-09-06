from pathlib import Path

import pytest

from modules.common.errors import ValidationAppError
from modules.material_qa.services import (
    MaterialDocumentValidator,
    QdrantMaterialIndexer,
    QdrantMaterialRetriever,
)


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


def test_hybrid_retrieval_fuses_exact_terms_and_restores_parent_context() -> None:
    retriever = QdrantMaterialRetriever(documents={}, qdrant_path=Path("qdrant"), embedding_model="test")
    article = {
        "source_id": "article",
        "page_content": "Transformer 课程概览。",
        "metadata": {"chunk_type": "article_card", "content_unit_id": "dl-unit-018"},
    }
    child = {
        "source_id": "child-1",
        "page_content": "Transformer 的 self-attention 使用 query、key 和 value。",
        "metadata": {
            "chunk_type": "child",
            "content_unit_id": "dl-unit-018",
            "parent_id": "dl-unit-018:section:1",
            "chunk_index": 1,
        },
    }
    sibling = {
        "source_id": "child-2",
        "page_content": "attention 的输出用于后续的前馈网络。",
        "metadata": {**child["metadata"], "chunk_index": 2},
    }

    lexical = retriever._lexical_candidates(question="Transformer 的 query 是什么？", corpus=[article, child, sibling], limit=3)
    fused = retriever._rrf_fuse(dense_entries=[{**article, "score": 0.8}], lexical_entries=lexical, source_ids=None)
    expanded = retriever._expand_parent_context(seeds=[next(item for item in fused if item["source_id"] == "child-1")], corpus=[article, child, sibling], limit=8)

    assert lexical[0]["source_id"] == "child-1"
    assert {item["source_id"] for item in expanded} == {"article", "child-1", "child-2"}


def test_qdrant_hybrid_retrieval_end_to_end_in_memory(monkeypatch) -> None:
    from langchain_core.embeddings import Embeddings
    from qdrant_client import QdrantClient

    class TestEmbeddings(Embeddings):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [self.embed_query(text) for text in texts]

        def embed_query(self, text: str) -> list[float]:
            return [float(len(text) % 7), 1.0, 0.5]

    class ActiveRegistry:
        def acquire_lease(self, _book_id: str):
            return "hybrid-e2e-v1", "hybrid_e2e", "lease-1"

        def release_lease(self, **_kwargs) -> None:
            pass

    root = Path(__file__).parent / "fixtures" / "material_qa"
    client = QdrantClient(":memory:")
    retriever = QdrantMaterialRetriever(documents={"dl": root}, qdrant_path=Path("qdrant"), embedding_model="test")
    monkeypatch.setattr(retriever, "_resources", lambda: (client, TestEmbeddings()))
    retriever.indexer.build(
        book_id="dl",
        document_path=root,
        embeddings=TestEmbeddings(),
        client=client,
        collection_name="hybrid_e2e",
    )
    retriever.registry = ActiveRegistry()  # type: ignore[assignment]

    result = retriever.retrieve(book_id="dl", question="transformer-query-key-value 是什么？")

    assert result.chunks
    assert len(result.chunks) <= 8
    assert any("文章目录" in chunk.text for chunk in result.chunks)
    assert any("transformer-query-key-value" in chunk.text for chunk in result.chunks)
    assert {chunk.source.index_version for chunk in result.chunks} == {"hybrid-e2e-v1"}


def test_context_prefix_and_stable_ids_are_deterministic() -> None:
    context = QdrantMaterialIndexer._context_prefix(
        "机器学习概览",
        ["ml-learning-task"],
        "理解机器学习任务。",
        "区分监督学习和无监督学习。",
    )

    assert "知识点文章：机器学习概览" in context
    assert "学习目标：理解机器学习任务。" in context
    assert QdrantMaterialIndexer._stable_id("ml", Path("lesson.md"), "0", 1) == QdrantMaterialIndexer._stable_id(
        "ml", Path("lesson.md"), "0", 1
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("5-NLP/18-Transformers/README.md", True),
        ("1-Intro/README.md", True),
        ("5-NLP/README.md", False),
        ("5-NLP/18-Transformers/lab/README.md", False),
        ("5-NLP/18-Transformers/assignment.md", False),
        ("sketchnotes/README.md", False),
    ],
)
def test_dl_candidate_keeps_only_numbered_lesson_readmes(path: str, expected: bool) -> None:
    root = Path("AI-For-Beginners/lessons")

    assert QdrantMaterialIndexer.is_course_article_candidate(
        book_id="dl",
        document_root=root,
        source_path=root / path,
    ) is expected


def test_dl_normalised_file_uses_its_readme_source_path() -> None:
    root = Path("AI-For-Beginners/lessons")

    assert QdrantMaterialIndexer.is_course_article_candidate(
        book_id="dl",
        document_root=root,
        source_path=root / "dl-unit-018.md",
        source_relative_path="lessons/5-NLP/18-Transformers/README.md",
    )


def _approved_dl_unit() -> str:
    return """---
content_unit_id: dl-unit-001
book_id: dl-001
topic_id: kp-ai-lesson-01
chapter: AI Foundations
knowledge_points: [kp-ai-lesson-01]
source_id: src-microsoft-ai-for-beginners
source_relative_path: lessons/1-Intro/README.md
source_commit: abc123
license: MIT
source_url: https://example.test/lesson-1
attribution: Microsoft AI-For-Beginners
cleaning_status: approved
review_status: approved
reviewer: content-editor
reviewed_at: 2026-09-05T00:00:00Z
review_method: editorial-audit-v1
---

# AI introduction

## 学习目标

Understand the definition.

## 阅读重点

Core concepts.

## 原文学习材料

# Introduction to AI

## Definition

Artificial intelligence is the study of intelligent systems.
"""


def test_validator_excludes_raw_markdown_and_accepts_reviewed_unit(tmp_path: Path) -> None:
    (tmp_path / "1-Intro").mkdir()
    (tmp_path / "1-Intro" / "README.md").write_text("# Raw course source", encoding="utf-8")
    (tmp_path / "dl-unit-001.md").write_text(_approved_dl_unit(), encoding="utf-8")

    report = MaterialDocumentValidator().validate_tree(book_id="dl", document_root=tmp_path)

    assert report["approved_count"] == 1
    assert report["error_count"] == 0
    assert report["excluded_count"] == 1


def test_review_transition_is_atomic_and_validated(tmp_path: Path) -> None:
    unit = tmp_path / "dl-unit-001.md"
    unit.write_text(_approved_dl_unit().replace("approved", "pending_review"), encoding="utf-8")
    retriever = QdrantMaterialRetriever(documents={"dl": tmp_path}, qdrant_path=tmp_path / "qdrant")

    result = retriever.review_unit(
        book_id="dl",
        content_unit_id="dl-unit-001",
        status="approved",
        reviewer="reviewer-1",
    )

    assert result["status"] == "approved"
    saved = unit.read_text(encoding="utf-8")
    assert "review_status: approved" in saved
    assert "reviewer: reviewer-1" in saved


def test_rebuild_activates_new_collection_only_after_acceptance(tmp_path: Path, monkeypatch) -> None:
    from langchain_core.embeddings import Embeddings
    from qdrant_client import QdrantClient

    class TestEmbeddings(Embeddings):
        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [self.embed_query(text) for text in texts]

        def embed_query(self, text: str) -> list[float]:
            return [float(len(text) % 7), 1.0, 0.5]

    (tmp_path / "dl-unit-001.md").write_text(_approved_dl_unit(), encoding="utf-8")
    client = QdrantClient(":memory:")
    retriever = QdrantMaterialRetriever(documents={"dl": tmp_path}, qdrant_path=tmp_path / "qdrant")
    monkeypatch.setattr(retriever, "_resources", lambda: (client, TestEmbeddings()))

    stats = retriever.rebuild(book_ids=["dl"])

    collection_name = str(stats[0]["collection_name"])
    assert stats[0]["activated"] is True
    assert client.collection_exists(collection_name)
    assert retriever.registry.active_collection("dl") == collection_name
    assert Path(str(stats[0]["report_path"])).exists()

    result = retriever.retrieve(book_id="dl", question="Artificial intelligence 的 Definition 是什么？")

    assert result.chunks
    assert any(chunk.source.contentUnitId == "dl-unit-001" for chunk in result.chunks)
    assert any("文章目录" in chunk.text for chunk in result.chunks)
