from __future__ import annotations

from pathlib import Path
from uuid import uuid4
import csv

from modules.common.errors import ResourceNotFoundError


class QdrantMaterialIndexer:
    """使用 LangChain 组件完成 PDF 切分、向量化和 Qdrant 建索引。"""

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
        """读取 PDF，并使用 LangChain 的 Document、Splitter 和 QdrantVectorStore 建索引。"""

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
            for chunk_index, chunk in enumerate(splitter.split_text(text.split("---", 2)[-1] if text.startswith("---") else text)):
                source_id = str(uuid4())
                content_unit_id = str(metadata.get("content_unit_id", source_path.stem))
                relation = self._content_relation(document_path, content_unit_id)
                knowledge_points = relation["knowledge_point_ids"] or ["unknown"]
                documents.append(
                    Document(
                        page_content=chunk,
                        metadata={
                            "source_id": source_id,
                            "book_id": book_id,
                            "book_title": {"ml": "《机器学习》", "dl": "《深度学习》"}.get(book_id, book_id),
                            "title": source_path.stem,
                            "location": str(source_path.relative_to(document_path.parent if document_path.is_dir() else document_path.parent)),
                            "chunk_index": chunk_index,
                            "content_unit_id": content_unit_id,
                            "chapter_id": relation["chapter_id"],
                            "section_id": relation["section_id"],
                            "knowledge_point_ids": knowledge_points,
                        },
                    )
                )
                ids.append(source_id)

        if documents:
            vector_store = QdrantVectorStore(
                client=client,
                collection_name=collection_name,
                embedding=embeddings,
            )
            vector_store.add_documents(documents=documents, ids=ids)

    @staticmethod
    def _content_relation(document_path: Path, content_unit_id: str) -> dict[str, object]:
        """Resolve a formal content unit to its chapter, section and knowledge points."""
        data_dir = next((parent / "data" for parent in document_path.parents if (parent / "data").is_dir()), None)
        result: dict[str, object] = {"chapter_id": "", "section_id": "", "knowledge_point_ids": []}
        if data_dir is None:
            return result

        def rows(name: str) -> list[dict[str, str]]:
            with (data_dir / name).open(encoding="utf-8-sig", newline="") as handle:
                return list(csv.DictReader(handle))

        units = next((row for row in rows("content_unit_catalog.csv") if row.get("content_unit_id") == content_unit_id), None)
        if units:
            result["chapter_id"] = units.get("chapter_id", "")
        sections = next((row for row in rows("section_catalog.csv") if row.get("content_unit_id") == content_unit_id), None)
        if sections:
            result["section_id"] = sections.get("section_id", "")
            result["chapter_id"] = sections.get("chapter_id", result["chapter_id"])
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
            if key.strip() == "knowledge_points":
                result[key.strip()] = [item.strip() for item in value.strip("[]").split(",") if item.strip()]
            else:
                result[key.strip()] = value
        return result

    def collection_name(self, book_id: str) -> str:
        return f"study_companion_{book_id}"
