"""Services for material question answering, retrieval, and indexing."""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import math
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, RLock
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5

from pydantic import BaseModel, Field, ValidationError, model_validator

from modules.common.errors import ConflictError, ResourceNotFoundError, ValidationAppError, WorkflowStateError

from .models import (
    AnswerMode,
    MaterialQaAgentInput,
    MaterialQaAgentOutput,
    MaterialQaAnswer,
    MaterialQaConversation,
    MaterialQaMessage,
    MaterialQaRetrievedChunk,
    MaterialQaRetrievalResult,
    ResponseQuality,
    SocraticStateName,
)
from .schemas import MaterialQaSource
from .repository import InMemoryMaterialQaMessageStore, MaterialQaMessageStore


logger = logging.getLogger(__name__)


class MaterialQaActivityRecorder(Protocol):
    """Material QA 如果想记录“用户开始了一次资料问答”，外部记录器至少应该提供什么方法。"""

    def record_qa_started(self, *, user_id: str, book_id: str, conversation_id: str) -> object:
        ...

#负责管理一次问答操作中的业务数据
class MaterialQaService:
    """Own message-stream operations and material-QA input/output construction."""

    HISTORY_LIMIT = 12

    def __init__(
        self,
        message_store: MaterialQaMessageStore | None = None,
        activity_recorder: MaterialQaActivityRecorder | None = None,
    ) -> None:
        self.message_store = message_store or InMemoryMaterialQaMessageStore()
        self.activity_recorder = activity_recorder
    # 为前端生成一个临时的问答标识；如果用户明确点击了“清空对话”，就在数据库中插入上下文重置标记。
    def create_conversation(
        self,
        *,
        book_id: str,
        user_id: str,
        reset_context: bool = False,
    ) -> MaterialQaConversation:
        # conversation_id is retained as an API/UI request token only. Persistent
        # history is intentionally grouped by user_id + book_id instead.
        conversation = MaterialQaConversation(
            conversation_id=f"qa-{uuid4().hex[:12]}",
            book_id=book_id,
            user_id=user_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        if reset_context:
            self.message_store.reset_context(user_id=user_id, book_id=book_id)
        else:
            conversation.active_learning_task = self.message_store.get_active_learning_task(
                user_id=user_id,
                book_id=book_id,
            )
        if self.activity_recorder is not None:
            self.activity_recorder.record_qa_started(
                user_id=user_id,
                book_id=book_id,
                conversation_id=conversation.conversation_id,
            )
        return conversation

    # Prepare the model history before the current question is persisted.
    def begin_question(
        self,
        *,
        user_id: str,
        book_id: str,
    ) -> list[MaterialQaMessage]:
        return self.message_store.list_recent(
            user_id=user_id,
            book_id=book_id,
            limit=self.HISTORY_LIMIT,
        )

    #Agent生成结果后，更新会话
    def complete_question(
        self,
        *,
        conversation_id: str,
        user_id: str,
        book_id: str,
        question: str,
        output: MaterialQaAgentOutput,
    ) -> MaterialQaAnswer:
        self.message_store.save_exchange(
            user_id=user_id,
            book_id=book_id,
            question=question,
            answer=output.answer,
            citations=output.citations,
            answer_mode=output.answer_mode,
            learning_task_id=output.learning_task_id,
            socratic_state=output.socratic_state,
            response_quality=output.response_quality,
            socratic_completed=output.socratic_completed,
        )
        return MaterialQaAnswer(
            conversation_id=conversation_id,
            answer=output.answer,
            refused=output.refused,
            citations=output.citations,
            related_knowledge_points=output.related_knowledge_points,
            recommended_action=output.recommended_action,
            answered_by_general_model=output.answered_by_general_model,
            answer_mode=output.answer_mode,
            learning_task_id=output.learning_task_id,
            socratic_state=output.socratic_state,
            response_quality=output.response_quality,
            socratic_completed=output.socratic_completed,
        )

    @staticmethod
    def agent_input(
        *,
        history: list[MaterialQaMessage],
        question: str,
        retrieval: MaterialQaRetrievalResult,
        allow_general_fallback: bool = False,
        answer_mode: AnswerMode = "direct",
        learning_task_id: str | None = None,
        socratic_state: SocraticStateName | None = None,
        socratic_directive: str = "",
        root_question: str = "",
    ) -> MaterialQaAgentInput:
        return MaterialQaAgentInput(
            history=history,
            current_question=question,
            retrieval=retrieval,
            allow_general_fallback=allow_general_fallback,
            answer_mode=answer_mode,
            learning_task_id=learning_task_id,
            socratic_state=socratic_state,
            socratic_directive=socratic_directive,
            root_question=root_question,
        )

    def finish_learning_task(self, *, user_id: str, book_id: str, learning_task_id: str) -> None:
        self.message_store.finish_learning_task(
            user_id=user_id,
            book_id=book_id,
            learning_task_id=learning_task_id,
        )


#负责把原始学习资料加工并写入 Qdrant
class QdrantMaterialIndexer:
    """Parse formal Markdown material and build its Qdrant index."""

    # v5: only reviewed course material, heading-aware children, and article cards.
    INDEX_SCHEMA_VERSION = 5
    ORIGINAL_MATERIAL_HEADING = "原文学习材料"

    def __init__(
        self,
        *,
        qdrant_path: Path,
        embedding_model: str,
        chunk_size: int = 1200,
        overlap: int = 200,
    ) -> None:
        self.qdrant_path = qdrant_path
        self.embedding_model = embedding_model
        self.chunk_size = chunk_size
        self.overlap = overlap

    def build(
        self,
        *,
        book_id: str,
        document_path: Path,
        embeddings,
        client,
        collection_name: str | None = None,
        source_paths: set[Path] | None = None,
        create_collection: bool = True,
    ) -> dict[str, object]:
        try:
            from langchain_core.documents import Document
            from langchain_qdrant import QdrantVectorStore
            from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
            from qdrant_client.models import Distance, VectorParams
        except ImportError as exc:
            raise RuntimeError("RAG dependencies are not installed; install requirements.txt first") from exc

        if not document_path.exists():
            raise ResourceNotFoundError("material document not found", details={"path": str(document_path)})

        collection_name = collection_name or self.collection_name(book_id)
        if client.collection_exists(collection_name) and create_collection:
            raise WorkflowStateError(
                "refusing to overwrite an existing material index collection",
                details={"collection_name": collection_name},
            )
        if not client.collection_exists(collection_name):
            dimension = len(embeddings.embed_query("embedding dimension probe"))
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
            )
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.overlap,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
            keep_separator=True,
            strip_whitespace=True,
        )

        documents: list[Document] = []
        ids: list[str] = []
        indexed_articles = 0
        header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("#", "h1"), ("##", "h2"), ("###", "h3")],
            strip_headers=False,
        )
        paths = [document_path] if document_path.is_file() else sorted(document_path.rglob("*.md"))
        if source_paths is not None:
            paths = [path for path in paths if path.resolve() in source_paths]
        for source_path in paths:
            text = source_path.read_text(encoding="utf-8").strip()
            metadata = self._markdown_metadata(text)
            if not self.is_course_article_candidate(
                book_id=book_id,
                document_root=document_path,
                source_path=source_path,
                source_relative_path=str(metadata.get("source_relative_path", "")),
            ):
                continue
            # Do not silently ingest repository documentation, translations, or drafts.
            if metadata.get("cleaning_status") != "approved" or metadata.get("review_status") != "approved":
                continue
            try:
                original_material = self._extract_original_material(text, source_path=source_path)
            except ValidationAppError:
                continue
            content_unit_id = str(metadata.get("content_unit_id", source_path.stem))
            relation = self._content_relation(document_path, content_unit_id)
            knowledge_points = relation["knowledge_point_ids"] or list(metadata.get("knowledge_points", [])) or ["unknown"]
            title = self._first_heading(text) or self._first_heading(original_material) or source_path.stem
            learning_goal = self._named_section(text, "学习目标")
            reading_focus = self._named_section(text, "阅读重点")
            base_metadata = self._base_metadata(
                book_id=book_id,
                document_path=document_path,
                source_path=source_path,
                metadata=metadata,
                content_unit_id=content_unit_id,
                title=title,
                knowledge_points=knowledge_points,
                relation=relation,
            )
            context = self._context_prefix(title, knowledge_points, learning_goal, reading_focus)
            article_id = self._stable_id(book_id, source_path, "article", 0)
            documents.append(Document(
                page_content=context + "\n文章目录：" + "；".join(section.metadata.get("h2", section.metadata.get("h1", "")) for section in header_splitter.split_text(original_material)),
                metadata={**base_metadata, "source_id": article_id, "chunk_type": "article_card", "parent_id": content_unit_id, "chunk_index": 0},
            ))
            ids.append(article_id)
            indexed_articles += 1
            for section_index, section in enumerate(header_splitter.split_text(original_material)):
                heading_path = [value for key in ("h1", "h2", "h3") if (value := section.metadata.get(key))]
                for chunk_index, chunk in enumerate(splitter.split_text(section.page_content)):
                    source_id = self._stable_id(book_id, source_path, str(section_index), chunk_index)
                    contextual_text = context + "\n标题路径：" + " > ".join(str(part) for part in heading_path) + "\n\n" + chunk
                    documents.append(
                        Document(
                            page_content=contextual_text,
                            metadata={
                                **base_metadata,
                                "source_id": source_id,
                                "chunk_type": "child",
                                "heading_path": heading_path,
                                "parent_id": f"{content_unit_id}:section:{section_index}",
                                "chunk_index": chunk_index,
                                "section_index": section_index,
                            },
                        )
                    )
                    ids.append(source_id)

        if documents:
            QdrantVectorStore(
                client=client,
                collection_name=collection_name,
                embedding=embeddings,
            ).add_documents(documents=documents, ids=ids, batch_size=64)
        return {
            "book_id": book_id,
            "collection_name": collection_name,
            "article_count": indexed_articles,
            "indexed_documents": len(documents),
        }

    @staticmethod
    def _stable_id(book_id: str, source_path: Path, section: str, chunk_index: int) -> str:
        return str(uuid5(NAMESPACE_URL, f"{book_id}:{source_path.as_posix()}:{section}:{chunk_index}"))

    @staticmethod
    def is_course_article_candidate(
        *,
        book_id: str,
        document_root: Path,
        source_path: Path,
        source_relative_path: str = "",
    ) -> bool:
        """Keep the AI-for-Beginners corpus to its English lesson README files.

        Normalised files may have names such as ``dl-unit-001.md``. For those
        files, ``source_relative_path`` is the authoritative source link.
        """
        if book_id != "dl":
            return True

        def is_lesson_readme(value: str) -> bool:
            normalised = value.replace("\\", "/").strip("/")
            parts = normalised.split("/")
            if not parts or parts[-1].lower() != "readme.md":
                return False
            blocked = {"translations", "lab", "sketchnotes", "examples", "0-course-setup", "x-extras"}
            if any(part.lower() in blocked for part in parts[:-1]):
                return False
            # These are chapter landing pages. The numbered README nested below
            # each one is the actual lesson mapped to the knowledge catalogue.
            if len(parts) == 2 and parts[0] in {"3-NeuralNetworks", "4-ComputerVision", "5-NLP"}:
                return False
            return any(re.fullmatch(r"\d{1,2}-.+", part) for part in parts[:-1])

        try:
            relative_path = source_path.relative_to(document_root).as_posix()
        except ValueError:
            relative_path = source_path.as_posix()
        return is_lesson_readme(relative_path) or is_lesson_readme(source_relative_path)

    @staticmethod
    def _first_heading(text: str) -> str:
        match = re.search(r"^#[ \t]+(.+?)\s*$", text, flags=re.MULTILINE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _named_section(text: str, name: str) -> str:
        match = re.search(rf"^##[ \t]+{re.escape(name)}[ \t]*$([\s\S]*?)(?=^##[ \t]+|\Z)", text, flags=re.MULTILINE)
        return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""

    @staticmethod
    def _context_prefix(title: str, knowledge_points: list[object], learning_goal: str, reading_focus: str) -> str:
        fields = [f"知识点文章：{title}", f"知识点：{', '.join(str(item) for item in knowledge_points)}"]
        if learning_goal:
            fields.append(f"学习目标：{learning_goal}")
        if reading_focus:
            fields.append(f"阅读重点：{reading_focus}")
        return "\n".join(fields)

    @classmethod
    def _base_metadata(
        cls,
        *,
        book_id: str,
        document_path: Path,
        source_path: Path,
        metadata: dict[str, object],
        content_unit_id: str,
        title: str,
        knowledge_points: list[object],
        relation: dict[str, object],
    ) -> dict[str, object]:
        return {
            "source_document_id": str(metadata.get("source_id", "")),
            "book_id": book_id,
            "source_book_id": str(metadata.get("book_id", "")),
            "book_title": {"ml": "《机器学习》", "dl": "《深度学习》"}.get(book_id, book_id),
            "title": title,
            "location": str(source_path.relative_to(document_path.parent)),
            "content_unit_id": content_unit_id,
            "topic_id": str(metadata.get("topic_id", "")),
            "chapter": str(metadata.get("chapter", "")),
            "knowledge_points": [str(item) for item in metadata.get("knowledge_points", [])],
            "source_relative_path": str(metadata.get("source_relative_path", "")),
            "source_commit": str(metadata.get("source_commit", "")),
            "license": str(metadata.get("license", "")),
            "source_url": str(metadata.get("source_url", "")),
            "attribution": str(metadata.get("attribution", "")),
            "cleaning_status": str(metadata.get("cleaning_status", "")),
            "review_status": str(metadata.get("review_status", "")),
            "reviewer": str(metadata.get("reviewer", "")),
            "reviewed_at": str(metadata.get("reviewed_at", "")),
            "review_method": str(metadata.get("review_method", "")),
            "chapter_id": str(relation["chapter_id"]),
            "section_id": str(relation["section_id"]),
            "knowledge_point_ids": [str(item) for item in knowledge_points],
            "index_schema_version": cls.INDEX_SCHEMA_VERSION,
        }

    @staticmethod
    def _content_relation(document_path: Path, content_unit_id: str) -> dict[str, object]:
        data_dir = next((parent / "data" for parent in document_path.parents if (parent / "data").is_dir()), None)
        result: dict[str, object] = {"chapter_id": "", "section_id": "", "knowledge_point_ids": []}
        if data_dir is None:
            return result

        def rows(name: str) -> list[dict[str, str]]:
            path = data_dir / name
            if not path.exists():
                return []
            with path.open(encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle))

        unit = next((row for row in rows("content_unit_catalog.csv") if row.get("content_unit_id") == content_unit_id), None)
        if unit:
            result["chapter_id"] = unit.get("chapter_id", "")
        section = next((row for row in rows("section_catalog.csv") if row.get("content_unit_id") == content_unit_id), None)
        if section:
            result["section_id"] = section.get("section_id", "")
            result["chapter_id"] = section.get("chapter_id", result["chapter_id"])
        result["knowledge_point_ids"] = [
            row.get("knowledge_point_id", "")
            for row in rows("content_unit_knowledge_edges.csv")
            if row.get("content_unit_id") == content_unit_id and row.get("knowledge_point_id")
        ]
        return result

    @staticmethod
    def _markdown_metadata(text: str) -> dict[str, object]:
        if not text.startswith("---"):
            return {}
        header = text.split("---", 2)[1]
        result: dict[str, object] = {}
        for line in header.splitlines():
            key, separator, value = line.partition(":")
            if not separator:
                continue
            value = value.strip()
            result[key.strip()] = (
                [item.strip() for item in value.strip("[]").split(",") if item.strip()]
                if key.strip() == "knowledge_points"
                else value
            )
        return result

    @classmethod
    def _extract_original_material(
        cls,
        text: str,
        *,
        source_path: Path,
        allow_plain_markdown: bool = False,
    ) -> str:
        heading = re.compile(
            rf"^##[ \t]+{re.escape(cls.ORIGINAL_MATERIAL_HEADING)}[ \t]*$",
            flags=re.MULTILINE,
        )
        match = heading.search(text)
        if match is None and not allow_plain_markdown:
            raise ValidationAppError(
                "material document is missing the original material section",
                details={"path": str(source_path), "heading": f"## {cls.ORIGINAL_MATERIAL_HEADING}"},
            )
        original_material = text[match.end():].strip() if match else text.strip()
        if not original_material:
            raise ValidationAppError("original material section is empty", details={"path": str(source_path)})
        return original_material

    def collection_needs_rebuild(self, *, client, collection_name: str) -> bool:
        if not client.collection_exists(collection_name):
            return True
        points, _ = client.scroll(
            collection_name=collection_name,
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            return True
        metadata = (points[0].payload or {}).get("metadata", {})
        return metadata.get("index_schema_version") != self.INDEX_SCHEMA_VERSION

    @staticmethod
    def collection_name(book_id: str) -> str:
        return f"study_companion_v5_{book_id}"


class MaterialDocumentSchema(BaseModel):
    """The reviewed-document contract required before a unit can be indexed."""

    content_unit_id: str = Field(pattern=r"^(ml|dl)-unit-\d{3}$")
    book_id: Literal["ml-001", "dl-001"]
    topic_id: str = Field(min_length=1)
    chapter: str = Field(min_length=1)
    knowledge_points: list[str] = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_relative_path: str = Field(min_length=1)
    source_commit: str = Field(min_length=1)
    license: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    cleaning_status: Literal["pending_review", "approved", "rejected"]
    review_status: Literal["pending_review", "approved", "rejected"]
    reviewer: str = ""
    reviewed_at: str = ""
    review_method: str = Field(min_length=1)
    review_reason: str = ""
    original_material: str = Field(min_length=1, exclude=True)

    @model_validator(mode="after")
    def review_fields_match_status(self) -> "MaterialDocumentSchema":
        if self.cleaning_status != self.review_status:
            raise ValueError("cleaning_status and review_status must match")
        if self.review_status == "approved" and (not self.reviewer or not self.reviewed_at):
            raise ValueError("approved material requires reviewer and reviewed_at")
        if self.review_status == "rejected" and not self.review_reason:
            raise ValueError("rejected material requires review_reason")
        return self


class MaterialDocumentValidator:
    """Validate formal Markdown units and emit a machine-readable audit report."""

    def validate_tree(self, *, book_id: str, document_root: Path) -> dict[str, object]:
        approved: list[Path] = []
        pending: list[str] = []
        excluded: list[dict[str, str]] = []
        errors: list[dict[str, object]] = []
        for path in sorted(document_root.rglob("*.md")):
            text = path.read_text(encoding="utf-8", errors="strict").strip()
            metadata = QdrantMaterialIndexer._markdown_metadata(text)
            if not metadata.get("content_unit_id"):
                excluded.append({"path": str(path.relative_to(document_root)), "reason": "raw_or_unmanaged_markdown"})
                continue
            if not QdrantMaterialIndexer.is_course_article_candidate(
                book_id=book_id,
                document_root=document_root,
                source_path=path,
                source_relative_path=str(metadata.get("source_relative_path", "")),
            ):
                excluded.append({"path": str(path.relative_to(document_root)), "reason": "not_a_course_readme_source"})
                continue
            try:
                original_material = QdrantMaterialIndexer._extract_original_material(text, source_path=path)
                schema = MaterialDocumentSchema.model_validate({**metadata, "original_material": original_material})
                if schema.book_id != {"ml": "ml-001", "dl": "dl-001"}[book_id]:
                    raise ValueError(f"book_id {schema.book_id!r} does not match requested book {book_id!r}")
            except (ValidationAppError, ValidationError, UnicodeError) as exc:
                errors.append({"path": str(path.relative_to(document_root)), "errors": str(exc)})
                continue
            except ValueError as exc:
                errors.append({"path": str(path.relative_to(document_root)), "errors": str(exc)})
                continue
            if schema.review_status == "approved":
                approved.append(path)
            else:
                pending.append(str(path.relative_to(document_root)))
        return {
            "book_id": book_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "approved_documents": [str(path) for path in approved],
            "approved_count": len(approved),
            "pending_documents": pending,
            "pending_count": len(pending),
            "excluded": excluded,
            "excluded_count": len(excluded),
            "errors": errors,
            "error_count": len(errors),
        }

    def validate_document(self, *, book_id: str, document_root: Path, path: Path, text: str) -> MaterialDocumentSchema:
        metadata = QdrantMaterialIndexer._markdown_metadata(text)
        if not QdrantMaterialIndexer.is_course_article_candidate(
            book_id=book_id,
            document_root=document_root,
            source_path=path,
            source_relative_path=str(metadata.get("source_relative_path", "")),
        ):
            raise ValidationAppError("material source is not an eligible course README", details={"path": str(path)})
        original_material = QdrantMaterialIndexer._extract_original_material(text, source_path=path)
        try:
            schema = MaterialDocumentSchema.model_validate({**metadata, "original_material": original_material})
        except ValidationError as exc:
            raise ValidationAppError("material document schema validation failed", details={"path": str(path), "errors": exc.errors()}) from exc
        if schema.book_id != {"ml": "ml-001", "dl": "dl-001"}[book_id]:
            raise ValidationAppError("material document book_id does not match requested book", details={"path": str(path)})
        return schema


class MaterialIngestionReportStore:
    """Persist immutable ingestion reports beside runtime data for auditing."""

    def __init__(self, report_root: Path) -> None:
        self.report_root = report_root

    def write(self, report: dict[str, object]) -> Path:
        self.report_root.mkdir(parents=True, exist_ok=True)
        batch_id = str(report["batch_id"])
        target = self.report_root / f"{batch_id}.json"
        self._atomic_write(target, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return target

    @staticmethod
    def _atomic_write(target: Path, content: str) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, target)


class MaterialIndexRegistry:
    """Version registry with atomic activation and short-lived query leases."""

    _locks_guard = RLock()
    _locks: dict[str, RLock] = {}

    def __init__(self, path: Path) -> None:
        self.path = path
        with self._locks_guard:
            self._lock = self._locks.setdefault(str(path.resolve()), RLock())
        # Leases protect only in-flight requests. They intentionally stay in
        # memory: persisting two JSON writes per query is a major P95 regression,
        # while retired collections are never auto-deleted during a process run.
        self._active_cache: dict[str, dict[str, object] | None] = {}
        self._lease_counts: dict[tuple[str, str], int] = {}

    def active_version(self, book_id: str) -> dict[str, object] | None:
        with self._lock:
            if book_id in self._active_cache:
                cached = self._active_cache[book_id]
                return dict(cached) if cached else None
            data = self._read()
            book = data["books"].get(book_id, {})
            version_id = book.get("active_version")
            version = book.get("versions", {}).get(version_id) if version_id else None
            self._active_cache[book_id] = dict(version) if version else None
            return dict(version) if version else None

    def active_collection(self, book_id: str) -> str | None:
        version = self.active_version(book_id)
        return str(version.get("collection_name", "")) if version else None

    def active_manifest(self, book_id: str) -> dict[str, object]:
        version = self.active_version(book_id)
        return dict(version.get("manifest", {})) if version else {}

    def activate(
        self,
        *,
        book_id: str,
        version_id: str,
        collection_name: str,
        report_path: Path,
        manifest: dict[str, object],
    ) -> None:
        with self._lock:
            data = self._read()
            book = data["books"].setdefault(book_id, {"active_version": None, "versions": {}})
            previous_id = book.get("active_version")
            versions = book.setdefault("versions", {})
            if previous_id and previous_id in versions:
                versions[previous_id]["status"] = "retired"
                versions[previous_id]["retired_at"] = datetime.now(timezone.utc).isoformat()
            versions[version_id] = {
                "version_id": version_id,
                "collection_name": collection_name,
                "status": "active",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "report_path": str(report_path),
                "manifest": manifest,
                "active_leases": {},
            }
            book["active_version"] = version_id
            self._write(data)
            self._active_cache[book_id] = dict(versions[version_id])

    def acquire_lease(self, book_id: str) -> tuple[str | None, str | None, str | None]:
        with self._lock:
            version = self.active_version(book_id)
            if not version:
                return None, None, None
            lease_id = f"lease-{uuid4().hex}"
            version_id = str(version["version_id"])
            key = (book_id, version_id)
            self._lease_counts[key] = self._lease_counts.get(key, 0) + 1
            return version_id, str(version["collection_name"]), lease_id

    def release_lease(self, *, book_id: str, version_id: str | None, lease_id: str | None) -> None:
        if not version_id or not lease_id:
            return
        with self._lock:
            key = (book_id, version_id)
            if self._lease_counts.get(key, 0) <= 1:
                self._lease_counts.pop(key, None)
            else:
                self._lease_counts[key] -= 1

    def active_lease_count(self, *, book_id: str, version_id: str) -> int:
        with self._lock:
            return self._lease_counts.get((book_id, version_id), 0)

    def _write(self, data: dict[str, object]) -> None:
        MaterialIngestionReportStore._atomic_write(self.path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    def _read(self) -> dict[str, object]:
        if not self.path.exists():
            return {"schema_version": 2, "books": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            # Migrate the previous single-pointer format without invalidating an
            # already active v5 collection.
            if "books" not in data:
                books = {}
                for book_id, old in data.get("active", {}).items():
                    version_id = str(old.get("batch_id") or f"{book_id}-legacy")
                    books[book_id] = {
                        "active_version": version_id,
                        "versions": {version_id: {**old, "version_id": version_id, "status": "active", "manifest": {}, "active_leases": {}}},
                    }
                data = {"schema_version": 2, "books": books}
            return data
        except (OSError, json.JSONDecodeError) as exc:
            raise ValidationAppError("material index registry is invalid", details={"path": str(self.path)}) from exc


#定义检索能力
class MaterialQaRetriever(Protocol):
    def retrieve(
        self,
        *,
        book_id: str,
        question: str,
        source_ids: list[str] | None = None,
    ) -> MaterialQaRetrievalResult:
        ...


class MarkdownMaterialRetriever:
    """Dependency-free fallback when the local Qdrant store is unavailable."""

    def __init__(self, *, documents: dict[str, Path], top_k: int = 3) -> None:
        self.documents = documents
        self.top_k = top_k

    def start(self) -> None:
        """The fallback has no external process or model to initialise."""

    def close(self) -> None:
        return None

    def retrieve(self, *, book_id: str, question: str, history: list[MaterialQaMessage], source_ids: list[str] | None = None) -> MaterialQaRetrievalResult:
        del history
        root = self.documents.get(book_id)
        if root is None or not root.exists():
            raise ResourceNotFoundError("material document not found", details={"book_id": book_id})
        tokens = set(re.findall(r"[A-Za-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", question.lower()))
        candidates: list[tuple[int, Path, str]] = []
        eligible_paths = [
            path
            for path in root.rglob("*.md")
            if QdrantMaterialIndexer.is_course_article_candidate(
                book_id=book_id,
                document_root=root,
                source_path=path,
            )
        ]
        for path in eligible_paths[:500]:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore").strip()
            except OSError:
                continue
            score = sum(text.lower().count(token) for token in tokens)
            if score:
                candidates.append((score, path, text))
        if not candidates:
            candidates = [
                (0, path, path.read_text(encoding="utf-8", errors="ignore").strip())
                for path in eligible_paths[:1]
            ]
        chunks: list[MaterialQaRetrievedChunk] = []
        for score, path, text in sorted(candidates, key=lambda item: item[0], reverse=True)[:self.top_k]:
            relative = str(path.relative_to(root))
            source_id = hashlib.sha256(f"{book_id}:{relative}".encode()).hexdigest()[:16]
            if source_ids and source_id not in source_ids:
                continue
            source = MaterialQaSource(id=source_id, type="教材", title=path.stem, location=relative, excerpt=text[:280], knowledgePointIds=["unknown"], bookId=book_id, indexVersion="markdown-fallback")
            chunks.append(MaterialQaRetrievedChunk(text=text[:1800], source=source, score=float(score)))
        return MaterialQaRetrievalResult(chunks=chunks)


class ResilientMaterialRetriever:
    """Prefer semantic retrieval, but preserve the rest of the application on lock conflicts."""

    def __init__(self, primary: MaterialQaRetriever, fallback: MaterialQaRetriever) -> None:
        self.primary = primary
        self.fallback = fallback
        self._use_fallback = False

    def start(self) -> None:
        # Do not make API startup depend on a local vector-store lock or a
        # heavyweight embedding-model load.  The primary retriever remains an
        # optional request-time enhancement; ``retrieve`` already switches to
        # the local Markdown material if it cannot serve a request.
        start_fallback = getattr(self.fallback, "start", None)
        if callable(start_fallback):
            start_fallback()

    def close(self) -> None:
        for retriever in (self.primary, self.fallback):
            close = getattr(retriever, "close", None)
            if callable(close):
                close()

    def rebuild(self, *, book_ids: list[str] | None = None) -> list[dict[str, object]]:
        rebuild = getattr(self.primary, "rebuild", None)
        if not callable(rebuild):
            raise RuntimeError("the primary material retriever does not support index rebuilding")
        return rebuild(book_ids=book_ids)

    def review_unit(self, **kwargs: object) -> dict[str, object]:
        review = getattr(self.primary, "review_unit", None)
        if not callable(review):
            raise RuntimeError("the primary material retriever does not support material review")
        return review(**kwargs)  # type: ignore[no-any-return]

    def retrieve(self, **kwargs: object) -> MaterialQaRetrievalResult:
        if self._use_fallback:
            return self.fallback.retrieve(**kwargs)  # type: ignore[arg-type]
        try:
            return self.primary.retrieve(**kwargs)  # type: ignore[arg-type]
        except Exception as exc:
            self._use_fallback = True
            logger.warning("Qdrant retrieval failed during a request; switching to Markdown fallback: %s", exc)
            return self.fallback.retrieve(**kwargs)  # type: ignore[arg-type]

#实际检索模块
class QdrantMaterialRetriever:
    """Ensure the material index is ready, then retrieve matching chunks."""

    _build_locks_guard = RLock()
    _build_locks: dict[str, Lock] = {}

    def __init__(
        self,
        *,
        documents: dict[str, Path],
        qdrant_path: Path,
        embedding_model: str = "BAAI/bge-m3",
        top_k: int = 5,
        candidate_k: int = 20,
        reranker_model: str | None = None,
        indexer: QdrantMaterialIndexer | None = None,
    ) -> None:
        self.documents = documents
        self.qdrant_path = qdrant_path
        self.embedding_model_name = embedding_model
        self.top_k = top_k
        self.candidate_k = max(candidate_k, top_k)
        self.reranker_model_name = reranker_model or os.getenv("STUDY_COMPANION_RERANKER_MODEL", "")
        self._embeddings = None
        self._client = None
        self._vector_stores: dict[str, object] = {}
        self._collection_snapshots: dict[str, list[dict[str, object]]] = {}
        self._reranker = None
        self._empty_books: set[str] = set()
        self.indexer = indexer or QdrantMaterialIndexer(
            qdrant_path=qdrant_path,
            embedding_model=embedding_model,
        )
        self.validator = MaterialDocumentValidator()
        self.report_store = MaterialIngestionReportStore(qdrant_path.parent / "material-reports")
        self.registry = MaterialIndexRegistry(qdrant_path / "material_index_registry.json")

    @classmethod
    def _build_lock(cls, book_id: str) -> Lock:
        with cls._build_locks_guard:
            return cls._build_locks.setdefault(book_id, Lock())

    def start(self) -> None:
        """Load the embedding model and open Qdrant during application startup."""

        self._resources()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        self._client = None
        self._embeddings = None
        self._vector_stores.clear()
        self._collection_snapshots.clear()
        self._reranker = None
        self._empty_books.clear()

    def rebuild(self, *, book_ids: list[str] | None = None) -> list[dict[str, object]]:
        """Serialize publication per book so concurrent rebuilds cannot race."""

        stats: list[dict[str, object]] = []
        for book_id in book_ids or list(self.documents):
            lock = self._build_lock(book_id)
            if not lock.acquire(blocking=False):
                raise ConflictError(
                    "a material index build is already running for this book",
                    details={"book_id": book_id},
                )
            try:
                stats.extend(self._rebuild_unlocked(book_ids=[book_id]))
            finally:
                lock.release()
        return stats

    def _rebuild_unlocked(self, *, book_ids: list[str] | None = None) -> list[dict[str, object]]:
        """Publish an immutable index version, re-embedding only changed units."""

        client, embeddings = self._resources()
        requested = book_ids or list(self.documents)
        stats: list[dict[str, object]] = []
        for book_id in requested:
            document_path = self.documents.get(book_id)
            if document_path is None:
                raise ResourceNotFoundError("material document not found", details={"book_id": book_id})
            version_id = f"{book_id}-v{self.indexer.INDEX_SCHEMA_VERSION}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
            validation = self.validator.validate_tree(book_id=book_id, document_root=document_path)
            report: dict[str, object] = {"batch_id": version_id, "phase": "validation", **validation}
            if int(validation["error_count"]) or not int(validation["approved_count"]):
                report["status"] = "blocked"
                report_path = self.report_store.write(report)
                raise ValidationAppError(
                    "material index build blocked by document validation",
                    details={"book_id": book_id, "report_path": str(report_path), "validation": validation},
                )
            approved_paths = {Path(path).resolve() for path in validation["approved_documents"]}
            manifest = self._document_manifest(
                book_id=book_id,
                document_root=document_path,
                paths=approved_paths,
                embedding_model=self.embedding_model_name,
            )
            previous = self.registry.active_version(book_id)
            previous_manifest = dict(previous.get("manifest", {})) if previous else {}
            previous_documents = dict(previous_manifest.get("documents", {}))
            current_documents = dict(manifest["documents"])
            same_embedding_model = previous_manifest.get("embedding_model") == manifest.get("embedding_model")
            unchanged_ids = {
                unit_id
                for unit_id, item in current_documents.items()
                if same_embedding_model and previous_documents.get(unit_id, {}).get("content_hash") == item["content_hash"]
            }
            changed_paths = {
                Path(item["path"]).resolve()
                for unit_id, item in current_documents.items()
                if unit_id not in unchanged_ids
            }
            deleted_ids = set(previous_documents) - set(current_documents)
            if previous and not changed_paths and not deleted_ids and same_embedding_model:
                report.update(
                    {
                        "status": "skipped_no_changes",
                        "phase": "deduplication",
                        "version_id": previous["version_id"],
                        "reused_documents": len(unchanged_ids),
                    }
                )
                report_path = self.report_store.write(report)
                stats.append(
                    {
                        "book_id": book_id,
                        "collection_name": previous["collection_name"],
                        "version_id": previous["version_id"],
                        "indexed_documents": client.count(collection_name=str(previous["collection_name"]), exact=True).count,
                        "reembedded_documents": 0,
                        "reused_documents": len(unchanged_ids),
                        "report_path": str(report_path),
                        "activated": False,
                        "skipped": True,
                    }
                )
                continue
            collection_name = f"{self.indexer.collection_name(book_id)}_{uuid4().hex[:12]}"
            # Create the empty target collection once. Unchanged vectors are copied
            # from the active version, then changed documents are re-embedded.
            self.indexer.build(
                book_id=book_id,
                document_path=document_path,
                embeddings=embeddings,
                client=client,
                collection_name=collection_name,
                source_paths=set(),
            )
            copied_points = 0
            if previous and unchanged_ids:
                copied_points = self._copy_unchanged_points(
                    client=client,
                    source_collection=str(previous["collection_name"]),
                    target_collection=collection_name,
                    unchanged_content_unit_ids=unchanged_ids,
                )
            built = self.indexer.build(
                book_id=book_id,
                document_path=document_path,
                embeddings=embeddings,
                client=client,
                collection_name=collection_name,
                source_paths=changed_paths,
                create_collection=False,
            )
            points = client.count(collection_name=collection_name, exact=True).count
            expected_articles = int(validation["approved_count"])
            expected_points = copied_points + int(built["indexed_documents"])
            if points != expected_points:
                report.update({"status": "failed_validation", "build": built, "qdrant_point_count": points})
                report_path = self.report_store.write(report)
                raise ValidationAppError(
                    "built material index did not pass acceptance checks",
                    details={"book_id": book_id, "report_path": str(report_path)},
                )
            build_summary = {
                "book_id": book_id,
                "collection_name": collection_name,
                "article_count": expected_articles,
                "indexed_documents": points,
                "reembedded_documents": int(built["article_count"]),
                "reused_documents": len(unchanged_ids),
                "reused_points": copied_points,
                "deleted_documents": len(deleted_ids),
            }
            report.update({"status": "activated", "phase": "build", "build": build_summary, "qdrant_point_count": points, "version_id": version_id})
            report_path = self.report_store.write(report)
            self.registry.activate(
                book_id=book_id,
                collection_name=collection_name,
                version_id=version_id,
                report_path=report_path,
                manifest=manifest,
            )
            self._empty_books.discard(book_id)
            stats.append({**build_summary, "version_id": version_id, "report_path": str(report_path), "activated": True})
        return stats

    @staticmethod
    def _document_manifest(
        *,
        book_id: str,
        document_root: Path,
        paths: set[Path],
        embedding_model: str,
    ) -> dict[str, object]:
        documents: dict[str, dict[str, str]] = {}
        for path in paths:
            text = path.read_text(encoding="utf-8")
            metadata = QdrantMaterialIndexer._markdown_metadata(text)
            original_material = QdrantMaterialIndexer._extract_original_material(text, source_path=path)
            content_unit_id = str(metadata["content_unit_id"])
            fingerprint = {
                "original_material": original_material,
                "title": QdrantMaterialIndexer._first_heading(text),
                "knowledge_points": metadata.get("knowledge_points", []),
                "source_commit": metadata.get("source_commit", ""),
                "index_schema_version": QdrantMaterialIndexer.INDEX_SCHEMA_VERSION,
            }
            documents[content_unit_id] = {
                "path": str(path),
                "content_hash": hashlib.sha256(json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
                "source_relative_path": str(metadata.get("source_relative_path", "")),
            }
        return {"book_id": book_id, "embedding_model": embedding_model, "documents": documents}

    @staticmethod
    def _copy_unchanged_points(*, client, source_collection: str, target_collection: str, unchanged_content_unit_ids: set[str]) -> int:
        from qdrant_client.models import PointStruct

        if not client.collection_exists(source_collection):
            return 0
        copied = 0
        offset = None
        while True:
            points, offset = client.scroll(
                collection_name=source_collection,
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            reusable = [
                PointStruct(id=point.id, vector=point.vector, payload=point.payload)
                for point in points
                if str((point.payload or {}).get("metadata", {}).get("content_unit_id", "")) in unchanged_content_unit_ids
            ]
            if reusable:
                client.upsert(collection_name=target_collection, points=reusable, wait=True)
                copied += len(reusable)
            if offset is None:
                break
        return copied

    def review_unit(
        self,
        *,
        book_id: str,
        content_unit_id: str,
        status: Literal["approved", "rejected", "pending_review"],
        reviewer: str,
        reason: str = "",
    ) -> dict[str, object]:
        document_root = self.documents.get(book_id)
        if document_root is None:
            raise ResourceNotFoundError("material document not found", details={"book_id": book_id})
        match: Path | None = None
        for path in document_root.rglob("*.md"):
            metadata = QdrantMaterialIndexer._markdown_metadata(path.read_text(encoding="utf-8"))
            if metadata.get("content_unit_id") == content_unit_id:
                match = path
                break
        if match is None:
            raise ResourceNotFoundError("material unit not found", details={"content_unit_id": content_unit_id})
        text = match.read_text(encoding="utf-8")
        current = str(QdrantMaterialIndexer._markdown_metadata(text).get("review_status", ""))
        allowed = {"pending_review": {"approved", "rejected"}, "rejected": {"pending_review"}}
        if status not in allowed.get(current, set()):
            raise WorkflowStateError("invalid material review status transition", details={"from": current, "to": status})
        if not reviewer:
            raise ValidationAppError("reviewer is required")
        updates = {
            "cleaning_status": status,
            "review_status": status,
            "reviewer": reviewer,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "review_reason": reason if status == "rejected" else "",
        }
        updated = self._replace_front_matter_fields(text, updates)
        if status == "approved":
            self.validator.validate_document(book_id=book_id, document_root=document_root, path=match, text=updated)
        MaterialIngestionReportStore._atomic_write(match, updated)
        return {"content_unit_id": content_unit_id, "status": status, "path": str(match)}

    @staticmethod
    def _replace_front_matter_fields(text: str, updates: dict[str, str]) -> str:
        if not text.startswith("---"):
            raise ValidationAppError("material document is missing front matter")
        parts = text.split("---", 2)
        if len(parts) != 3:
            raise ValidationAppError("material document front matter is invalid")
        lines = parts[1].splitlines()
        remaining = dict(updates)
        rewritten: list[str] = []
        for line in lines:
            key, separator, _ = line.partition(":")
            if separator and key in remaining:
                rewritten.append(f"{key}: {remaining.pop(key)}")
            else:
                rewritten.append(line)
        rewritten.extend(f"{key}: {value}" for key, value in remaining.items())
        return "---\n" + "\n".join(rewritten) + "\n---" + parts[2]

    def retrieve(
        self,
        *,
        book_id: str,
        question: str,
        source_ids: list[str] | None = None,
    ) -> MaterialQaRetrievalResult:
        from langchain_qdrant import QdrantVectorStore

        client, embeddings = self._resources()
        document_path = self.documents.get(book_id)
        if document_path is None:
            raise ResourceNotFoundError("material document not found", details={"book_id": book_id})
        if book_id in self._empty_books:
            return MaterialQaRetrievalResult(chunks=[])

        version_id, collection_name, lease_id = self.registry.acquire_lease(book_id)
        collection_name = collection_name or self.indexer.collection_name(book_id)
        if not client.collection_exists(collection_name):
            logger.warning("no active material index exists for book %s", book_id)
            self.registry.release_lease(book_id=book_id, version_id=version_id, lease_id=lease_id)
            return MaterialQaRetrievalResult(chunks=[])
        try:
            store = self._vector_stores.get(collection_name)
            if store is None:
                store = QdrantVectorStore(
                    client=client,
                    collection_name=collection_name,
                    embedding=embeddings,
                )
                self._vector_stores[collection_name] = store
            # Dense retrieval preserves semantic recall.  Lexical BM25 catches exact
            # course terminology, error codes, and identifiers that embedding-only
            # search can miss.  Both stages deliberately over-fetch before fusion.
            dense_entries = [
                self._entry_from_document(document, score)
                for document, score in store.similarity_search_with_score(question, k=self.candidate_k)
            ]
            corpus = self._collection_snapshot(client=client, collection_name=collection_name)
            lexical_entries = self._lexical_candidates(question=question, corpus=corpus, limit=self.candidate_k)
            fused = self._rrf_fuse(dense_entries=dense_entries, lexical_entries=lexical_entries, source_ids=source_ids)
            seeds = self._rerank(question=question, entries=fused)[: self.top_k]
            context_entries = self._expand_parent_context(seeds=seeds, corpus=corpus, limit=max(self.top_k, 8))
            chunks = [
                MaterialQaRetrievedChunk(
                    text=str(entry["page_content"]),
                    source=self._source_from_entry(entry=entry, document_name=document_path.name, book_id=book_id, version_id=version_id),
                    score=float(entry.get("score", entry.get("rrf_score", 0.0))),
                )
                for entry in context_entries
            ]
            return MaterialQaRetrievalResult(chunks=chunks)
        finally:
            self.registry.release_lease(book_id=book_id, version_id=version_id, lease_id=lease_id)

    @staticmethod
    def _entry_from_document(document, score: float) -> dict[str, object]:
        return {"source_id": str(document.metadata.get("source_id", "")), "page_content": document.page_content, "metadata": dict(document.metadata), "score": float(score)}

    def _collection_snapshot(self, *, client, collection_name: str) -> list[dict[str, object]]:
        """Cache payloads for lexical recall and parent/child context expansion."""

        cached = self._collection_snapshots.get(collection_name)
        if cached is not None:
            return cached
        entries: list[dict[str, object]] = []
        offset = None
        while True:
            points, offset = client.scroll(collection_name=collection_name, limit=256, offset=offset, with_payload=True, with_vectors=False)
            for point in points:
                payload = point.payload or {}
                metadata = dict(payload.get("metadata", {}))
                content = str(payload.get("page_content", ""))
                source_id = str(metadata.get("source_id", ""))
                if content and source_id:
                    entries.append({"source_id": source_id, "page_content": content, "metadata": metadata})
            if offset is None:
                break
        self._collection_snapshots[collection_name] = entries
        return entries

    @staticmethod
    def _search_tokens(text: str) -> list[str]:
        tokens: list[str] = []
        for match in re.findall(r"[A-Za-z0-9_+.-]{2,}|[\u4e00-\u9fff]+", text.lower()):
            tokens.append(match)
            if re.fullmatch(r"[\u4e00-\u9fff]+", match):
                tokens.extend(match[index : index + 2] for index in range(len(match) - 1))
        return tokens

    def _lexical_candidates(self, *, question: str, corpus: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
        query_tokens = self._search_tokens(question)
        if not query_tokens or not corpus:
            return []
        documents = [
            self._search_tokens(
                f"{entry['page_content']} {dict(entry['metadata']).get('title', '')} "
                f"{' '.join(map(str, dict(entry['metadata']).get('heading_path', [])))}"
            )
            for entry in corpus
        ]
        document_frequency: Counter[str] = Counter(token for tokens in documents for token in set(tokens))
        average_length = max(1.0, sum(len(tokens) for tokens in documents) / len(documents))
        total_documents = len(documents)
        scored: list[dict[str, object]] = []
        for entry, tokens in zip(corpus, documents):
            frequencies = Counter(tokens)
            score = 0.0
            for token in set(query_tokens):
                frequency = frequencies.get(token, 0)
                if not frequency:
                    continue
                idf = math.log(1.0 + (total_documents - document_frequency[token] + 0.5) / (document_frequency[token] + 0.5))
                score += idf * (frequency * 2.0) / (frequency + 1.2 * (1.0 - 0.75 + 0.75 * len(tokens) / average_length))
            if score:
                scored.append({**entry, "lexical_score": score})
        return sorted(scored, key=lambda entry: float(entry["lexical_score"]), reverse=True)[:limit]

    @staticmethod
    def _rrf_fuse(*, dense_entries: list[dict[str, object]], lexical_entries: list[dict[str, object]], source_ids: list[str] | None) -> list[dict[str, object]]:
        fused: dict[str, dict[str, object]] = {}
        for entries in (dense_entries, lexical_entries):
            for rank, entry in enumerate(entries, start=1):
                source_id = str(entry.get("source_id", ""))
                if not source_id or (source_ids and source_id not in source_ids):
                    continue
                candidate = fused.setdefault(source_id, dict(entry))
                candidate["rrf_score"] = float(candidate.get("rrf_score", 0.0)) + 1.0 / (60 + rank)
        return sorted(fused.values(), key=lambda entry: float(entry["rrf_score"]), reverse=True)

    def _rerank(self, *, question: str, entries: list[dict[str, object]]) -> list[dict[str, object]]:
        """Use a configured cross-encoder, with a deterministic lexical fallback."""

        if not entries:
            return []
        query_tokens = set(self._search_tokens(question))
        for entry in entries:
            metadata = dict(entry["metadata"])
            title_tokens = set(self._search_tokens(str(metadata.get("title", ""))))
            text_tokens = set(self._search_tokens(str(entry["page_content"])))
            coverage = len(query_tokens & text_tokens) / max(1, len(query_tokens))
            title_coverage = len(query_tokens & title_tokens) / max(1, len(query_tokens))
            entry["score"] = float(entry["rrf_score"]) + 0.02 * coverage + 0.01 * title_coverage
        reranker = self._load_reranker()
        if reranker is not None:
            try:
                scores = reranker.predict([(question, str(entry["page_content"])) for entry in entries])
                for entry, score in zip(entries, scores):
                    entry["score"] = float(entry["rrf_score"]) + float(score)
            except Exception as exc:  # A retrieval request must not fail because an optional model is unavailable.
                logger.warning("material reranker failed; using lexical fallback: %s", exc)
        return sorted(entries, key=lambda entry: float(entry["score"]), reverse=True)

    def _load_reranker(self):
        if self._reranker is False or not self.reranker_model_name:
            return None
        if self._reranker is None:
            try:
                from sentence_transformers import CrossEncoder

                self._reranker = CrossEncoder(self.reranker_model_name)
            except Exception as exc:
                self._reranker = False
                logger.warning("material reranker unavailable; using lexical fallback: %s", exc)
                return None
        return self._reranker

    @staticmethod
    def _expand_parent_context(*, seeds: list[dict[str, object]], corpus: list[dict[str, object]], limit: int) -> list[dict[str, object]]:
        expanded: list[dict[str, object]] = []
        seen: set[str] = set()

        def add(entry: dict[str, object], score: float) -> None:
            source_id = str(entry["source_id"])
            if source_id not in seen and len(expanded) < limit:
                seen.add(source_id)
                expanded.append({**entry, "score": score})

        for seed in seeds:
            seed_score = float(seed.get("score", 0.0))
            add(seed, seed_score)
            metadata = dict(seed["metadata"])
            if metadata.get("chunk_type") != "child":
                continue
            unit_id = str(metadata.get("content_unit_id", ""))
            parent_id = str(metadata.get("parent_id", ""))
            chunk_index = int(metadata.get("chunk_index", 0))
            article = next((entry for entry in corpus if dict(entry["metadata"]).get("chunk_type") == "article_card" and str(dict(entry["metadata"]).get("content_unit_id", "")) == unit_id), None)
            if article:
                add(article, seed_score - 0.001)
            siblings = sorted(
                (entry for entry in corpus if str(dict(entry["metadata"]).get("parent_id", "")) == parent_id and dict(entry["metadata"]).get("chunk_type") == "child"),
                key=lambda entry: abs(int(dict(entry["metadata"]).get("chunk_index", 0)) - chunk_index),
            )
            for sibling in siblings:
                if abs(int(dict(sibling["metadata"]).get("chunk_index", 0)) - chunk_index) <= 1:
                    add(sibling, seed_score - 0.002)
        return expanded

    @staticmethod
    def _source_from_entry(*, entry: dict[str, object], document_name: str, book_id: str, version_id: str | None) -> MaterialQaSource:
        metadata = dict(entry["metadata"])
        text = str(entry["page_content"])
        return MaterialQaSource(
            id=str(entry["source_id"]),
            type="教材",
            title=str(metadata.get("title", document_name)),
            location=str(metadata.get("location", "文本片段")),
            excerpt=text[:280],
            knowledgePointIds=list(metadata.get("knowledge_point_ids", [])),
            chapterId=str(metadata.get("chapter_id", "")),
            sectionId=str(metadata.get("section_id", "")),
            contentUnitId=str(metadata.get("content_unit_id", "")),
            bookId=str(metadata.get("book_id", book_id)),
            indexVersion=version_id or "legacy-v5",
        )

    def _resources(self):
        if self._client is None or self._embeddings is None:
            try:
                from langchain_huggingface import HuggingFaceEmbeddings
                from qdrant_client import QdrantClient
            except ImportError as exc:
                raise RuntimeError("RAG dependencies are not installed; install requirements.txt first") from exc
            try:
                self.qdrant_path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise RuntimeError(f"cannot create Qdrant directory: {self.qdrant_path}") from exc
            self._client = QdrantClient(path=str(self.qdrant_path))
            self._embeddings = HuggingFaceEmbeddings(
                model_name=self.embedding_model_name,
                encode_kwargs={"normalize_embeddings": True},
            )
        return self._client, self._embeddings
