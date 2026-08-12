from __future__ import annotations

from pathlib import Path
from typing import Protocol

from modules.common.errors import ResourceNotFoundError

from .indexer import QdrantMaterialIndexer
from .models import MaterialQaMessage, MaterialQaRetrievedChunk, MaterialQaRetrievalResult
from .schemas import MaterialQaSource


class MaterialQaRetriever(Protocol):
    """资料问答检索器接口。"""

    def retrieve(
        self,
        *,
        book_id: str,
        question: str,
        history: list[MaterialQaMessage],
        source_ids: list[str] | None = None,
    ) -> MaterialQaRetrievalResult:
        ...


class QdrantMaterialRetriever:
    """使用 LangChain HuggingFace Embeddings 和 QdrantVectorStore 检索资料。"""

    def __init__(
        self,
        *,
        documents: dict[str, Path],
        qdrant_path: Path,
        embedding_model: str = "BAAI/bge-m3",
        top_k: int = 5,
    ) -> None:
        self.documents = documents
        self.qdrant_path = qdrant_path
        self.embedding_model_name = embedding_model
        self.top_k = top_k
        self._embeddings = None
        self._client = None
        self._indexer = QdrantMaterialIndexer(
            qdrant_path=qdrant_path,
            embedding_model=embedding_model,
        )

    def start(self) -> None:
        """兼容旧启动流程；实际资源会在首次检索时按需初始化。"""

        return None

    def close(self) -> None:
        """释放 Qdrant 本地存储锁。"""

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

        collection_name = self._indexer.collection_name(book_id)
        if not client.collection_exists(collection_name):
            self._indexer.build(
                book_id=book_id,
                document_path=document_path,
                embeddings=embeddings,
                client=client,
            )

        vector_store = QdrantVectorStore(
            client=client,
            collection_name=collection_name,
            embedding=embeddings,
        )
        results = vector_store.similarity_search_with_score(question, k=self.top_k)

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
            chunks.append(
                MaterialQaRetrievedChunk(
                    text=document.page_content,
                    source=source,
                    score=float(score),
                )
            )
        return MaterialQaRetrievalResult(chunks=chunks)

    def _resources(self):
        if self._client is None or self._embeddings is None:
            try:
                from langchain_huggingface import HuggingFaceEmbeddings
                from qdrant_client import QdrantClient
            except ImportError as exc:
                raise RuntimeError("RAG dependencies are not installed; install requirements.txt first") from exc
            try:
                self.qdrant_path.parent.mkdir(parents=True, exist_ok=True)
                self.qdrant_path.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise RuntimeError(
                    f"无法创建 Qdrant 本地目录：{self.qdrant_path}。"
                    "请设置 STUDY_COMPANION_QDRANT_PATH 到可写目录，"
                    "或改用远程 Qdrant 服务。"
                ) from exc
            self._client = QdrantClient(path=str(self.qdrant_path))
            self._embeddings = HuggingFaceEmbeddings(
                model_name=self.embedding_model_name,
                encode_kwargs={"normalize_embeddings": True},
            )
        return self._client, self._embeddings
