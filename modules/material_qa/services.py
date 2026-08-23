"""Services for material question answering, retrieval, and indexing."""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from modules.common.errors import ResourceNotFoundError, ValidationAppError

from .models import (
    MaterialQaAgentInput,
    MaterialQaAgentOutput,
    MaterialQaAnswer,
    MaterialQaConversation,
    MaterialQaMessage,
    MaterialQaRetrievedChunk,
    MaterialQaRetrievalResult,
)
from .schemas import MaterialQaSource


class MaterialQaActivityRecorder(Protocol):
    """Material QA 如果想记录“用户开始了一次资料问答”，外部记录器至少应该提供什么方法。"""

    def record_qa_started(self, *, user_id: str, book_id: str, conversation_id: str) -> object:
        ...

#会话保存和读取
class MaterialQaConversationStore:
    """In-memory repository for concurrent material-QA conversations."""

    def __init__(self) -> None:
        self._conversations: dict[str, MaterialQaConversation] = {}

    def save(self, conversation: MaterialQaConversation) -> MaterialQaConversation:
        self._conversations[conversation.conversation_id] = conversation
        return conversation

    def get(self, conversation_id: str) -> MaterialQaConversation:
        try:
            return self._conversations[conversation_id]
        except KeyError as exc:
            raise ResourceNotFoundError(
                "material QA conversation not found",
                details={"conversation_id": conversation_id},
            ) from exc

#负责管理一次问答操作中的业务数据
class MaterialQaService:
    """Own conversation operations and material-QA input/output construction."""

    def __init__(
        self,
        store: MaterialQaConversationStore | None = None,
        activity_recorder: MaterialQaActivityRecorder | None = None,
    ) -> None:
        self.store = store or MaterialQaConversationStore()
        self.activity_recorder = activity_recorder

    def create_conversation(self, *, book_id: str, user_id: str) -> MaterialQaConversation:
        conversation = MaterialQaConversation(
            conversation_id=f"qa-{uuid4().hex[:12]}",
            book_id=book_id,
            user_id=user_id,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.save(conversation)
        if self.activity_recorder is not None:
            self.activity_recorder.record_qa_started(
                user_id=user_id,
                book_id=book_id,
                conversation_id=conversation.conversation_id,
            )
        return conversation

    #会话准备
    def begin_question(
        self,
        *,
        conversation_id: str,
        book_id: str,
        question: str,
    ) -> tuple[MaterialQaConversation, list[MaterialQaMessage]]:
        conversation = self.require_conversation(conversation_id, book_id)
        history = list(conversation.messages)
        conversation.messages.append(MaterialQaMessage(role="user", content=question))
        self.store.save(conversation)
        return conversation, history

    #Agent生成结果后，更新会话
    def complete_question(
        self,
        *,
        conversation: MaterialQaConversation,
        output: MaterialQaAgentOutput,
    ) -> MaterialQaAnswer:
        conversation.messages.append(MaterialQaMessage(role="assistant", content=output.answer))
        self.store.save(conversation)
        return MaterialQaAnswer(
            conversation_id=conversation.conversation_id,
            answer=output.answer,
            refused=output.refused,
            citations=output.citations,
            related_knowledge_points=output.related_knowledge_points,
            recommended_action=output.recommended_action,
            answered_by_general_model=output.answered_by_general_model,
        )

    #业务校验
    def require_conversation(self, conversation_id: str, book_id: str) -> MaterialQaConversation:
        conversation = self.store.get(conversation_id)
        if conversation.book_id != book_id:
            raise ValidationAppError(
                "conversation does not belong to the requested book",
                details={"conversation_id": conversation_id, "book_id": book_id},
            )
        return conversation

    @staticmethod
    def agent_input(
        *,
        history: list[MaterialQaMessage],
        question: str,
        retrieval: MaterialQaRetrievalResult,
        allow_general_fallback: bool = False,
    ) -> MaterialQaAgentInput:
        return MaterialQaAgentInput(
            history=history,
            current_question=question,
            retrieval=retrieval,
            allow_general_fallback=allow_general_fallback,
        )


#负责把原始学习资料加工并写入 Qdrant
class QdrantMaterialIndexer:
    """Parse formal Markdown material and build its Qdrant index."""

    INDEX_SCHEMA_VERSION = 4
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

    def build(self, *, book_id: str, document_path: Path, embeddings, client) -> None:
        try:
            from langchain_core.documents import Document
            from langchain_qdrant import QdrantVectorStore
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            from qdrant_client.models import Distance, VectorParams
        except ImportError as exc:
            raise RuntimeError("RAG dependencies are not installed; install requirements.txt first") from exc

        if not document_path.exists():
            raise ResourceNotFoundError("material document not found", details={"path": str(document_path)})

        collection_name = self.collection_name(book_id)
        if client.collection_exists(collection_name):
            client.delete_collection(collection_name)
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
        paths = [document_path] if document_path.is_file() else sorted(document_path.rglob("*.md"))
        for source_path in paths:
            text = source_path.read_text(encoding="utf-8").strip()
            metadata = self._markdown_metadata(text)
            original_material = self._extract_original_material(
                text,
                source_path=source_path,
                allow_plain_markdown=True,
            )
            for chunk_index, chunk in enumerate(splitter.split_text(original_material)):
                source_id = str(uuid4())
                content_unit_id = str(metadata.get("content_unit_id", source_path.stem))
                relation = self._content_relation(document_path, content_unit_id)
                knowledge_points = relation["knowledge_point_ids"] or ["unknown"]
                documents.append(
                    Document(
                        page_content=chunk,
                        metadata={
                            "source_id": source_id,
                            # front matter 中的 source_id/book_id 与应用的
                            # 文本块 source_id/book_id 语义不同，因此使用
                            # source_document_id/source_book_id 保留原始来源信息。
                            "source_document_id": str(metadata.get("source_id", "")),
                            "book_id": book_id,
                            "source_book_id": str(metadata.get("book_id", "")),
                            "book_title": {"ml": "《机器学习》", "dl": "《深度学习》"}.get(book_id, book_id),
                            "title": source_path.stem,
                            "location": str(source_path.relative_to(document_path.parent)),
                            "chunk_index": chunk_index,
                            "content_unit_id": content_unit_id,
                            "topic_id": str(metadata.get("topic_id", "")),
                            "chapter": str(metadata.get("chapter", "")),
                            "knowledge_points": list(metadata.get("knowledge_points", [])),
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
                            "chapter_id": relation["chapter_id"],
                            "section_id": relation["section_id"],
                            "knowledge_point_ids": knowledge_points,
                            "index_schema_version": self.INDEX_SCHEMA_VERSION,
                        },
                    )
                )
                ids.append(source_id)

        if documents:
            QdrantVectorStore(
                client=client,
                collection_name=collection_name,
                embedding=embeddings,
            ).add_documents(documents=documents, ids=ids)

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
        return f"study_companion_{book_id}"


#定义检索能力
class MaterialQaRetriever(Protocol):
    def retrieve(
        self,
        *,
        book_id: str,
        question: str,
        history: list[MaterialQaMessage],
        source_ids: list[str] | None = None,
    ) -> MaterialQaRetrievalResult:
        ...

#实际检索模块
class QdrantMaterialRetriever:
    """Ensure the material index is ready, then retrieve matching chunks."""

    def __init__(
        self,
        *,
        documents: dict[str, Path],
        qdrant_path: Path,
        embedding_model: str = "BAAI/bge-m3",
        top_k: int = 5,
        indexer: QdrantMaterialIndexer | None = None,
    ) -> None:
        self.documents = documents
        self.qdrant_path = qdrant_path
        self.embedding_model_name = embedding_model
        self.top_k = top_k
        self._embeddings = None
        self._client = None
        self.indexer = indexer or QdrantMaterialIndexer(
            qdrant_path=qdrant_path,
            embedding_model=embedding_model,
        )

    def start(self) -> None:
        """Load the embedding model and open Qdrant during application startup."""

        self._resources()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
        self._client = None
        self._embeddings = None

    def retrieve(
        self,
        *,
        book_id: str,
        question: str,
        history: list[MaterialQaMessage],
        source_ids: list[str] | None = None,
    ) -> MaterialQaRetrievalResult:
        del history
        from langchain_qdrant import QdrantVectorStore

        client, embeddings = self._resources()
        document_path = self.documents.get(book_id)
        if document_path is None:
            raise ResourceNotFoundError("material document not found", details={"book_id": book_id})

        collection_name = self.indexer.collection_name(book_id)
        if self.indexer.collection_needs_rebuild(client=client, collection_name=collection_name):
            self.indexer.build(
                book_id=book_id,
                document_path=document_path,
                embeddings=embeddings,
                client=client,
            )

        results = QdrantVectorStore(
            client=client,
            collection_name=collection_name,
            embedding=embeddings,
        ).similarity_search_with_score(question, k=self.top_k)
        chunks: list[MaterialQaRetrievedChunk] = []
        for document, score in results:
            metadata = document.metadata
            source_id = str(metadata.get("source_id", ""))
            if source_ids and source_id not in source_ids:
                continue
            source = MaterialQaSource(
                id=source_id,
                type="教材",
                title=str(metadata.get("title", document_path.name)),
                location=str(metadata.get("location", "文本片段")),
                excerpt=document.page_content[:280],
                knowledgePointIds=list(metadata.get("knowledge_point_ids", [])),
                chapterId=str(metadata.get("chapter_id", "")),
                sectionId=str(metadata.get("section_id", "")),
                contentUnitId=str(metadata.get("content_unit_id", "")),
                bookId=str(metadata.get("book_id", book_id)),
            )
            chunks.append(MaterialQaRetrievedChunk(text=document.page_content, source=source, score=float(score)))
        return MaterialQaRetrievalResult(chunks=chunks)

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
