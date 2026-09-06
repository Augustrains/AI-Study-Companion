"""Compare legacy full-rebuild behaviour with the versioned incremental publisher.

This is a controlled publish-pressure benchmark, not a replacement for the
HTTP Locust staging test. It uses an in-memory Qdrant instance and deliberately
adds embedding latency so duplicate work is measurable and reproducible.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from modules.common.errors import ConflictError
from modules.material_qa.services import QdrantMaterialIndexer, QdrantMaterialRetriever


class DelayedCountingEmbeddings(Embeddings):
    def __init__(self, document_delay_seconds: float, query_delay_seconds: float) -> None:
        self.document_delay_seconds = document_delay_seconds
        self.query_delay_seconds = query_delay_seconds
        self.document_texts = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.document_texts += len(texts)
        time.sleep(self.document_delay_seconds * len(texts))
        return [[float(len(text) % 11), 1.0, 0.5] for text in texts]

    def embed_query(self, text: str) -> list[float]:
        time.sleep(self.query_delay_seconds)
        return [float(len(text) % 11), 1.0, 0.5]


def write_unit(root: Path, number: int) -> None:
    source_number = number if number < 7 else number + 1
    root.joinpath(f"dl-unit-{number:03d}.md").write_text(
        f"""---
content_unit_id: dl-unit-{number:03d}
book_id: dl-001
topic_id: kp-ai-lesson-{number:02d}
chapter: AI Foundations
knowledge_points: [kp-ai-lesson-{number:02d}]
source_id: benchmark
source_relative_path: lessons/{source_number:02d}-Topic/README.md
source_commit: benchmark-{number}
license: MIT
source_url: https://example.test/{number}
attribution: benchmark
cleaning_status: approved
review_status: approved
reviewer: benchmark
reviewed_at: 2026-09-05
review_method: benchmark
---

# Lesson {number}

## 学习目标

Understand lesson {number}.

## 阅读重点

Core concepts for lesson {number}.

## 原文学习材料

# Lesson {number}

## Concept

This is stable benchmark course material for lesson {number}. It is deliberately
long enough to exercise the parent and child document index paths.
""",
        encoding="utf-8",
    )


def percentile(values: list[float], fraction: float) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[max(0, int(fraction * 100) - 1)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=int, default=12)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--embedding-delay-ms", type=float, default=8.0)
    parser.add_argument("--query-delay-ms", type=float, default=2.0)
    args = parser.parse_args()

    root = PROJECT_ROOT / ".tmp" / f"rag-publish-benchmark-{uuid4().hex}"
    root.mkdir(parents=True)
    for number in range(1, args.documents + 1):
        write_unit(root, number)
    delay = args.embedding_delay_ms / 1000
    query_delay = args.query_delay_ms / 1000

    # Baseline: the pre-versioning behaviour re-embeds every document on every
    # publish request, even if the files are unchanged.
    baseline_client = QdrantClient(":memory:")
    baseline_embeddings = DelayedCountingEmbeddings(delay, query_delay)
    indexer = QdrantMaterialIndexer(qdrant_path=root / "baseline-qdrant", embedding_model="benchmark")
    baseline_times: list[float] = []
    for repeat in range(args.repeats):
        started = time.perf_counter()
        indexer.build(
            book_id="dl",
            document_path=root,
            embeddings=baseline_embeddings,
            client=baseline_client,
            collection_name=f"baseline_{repeat}",
        )
        baseline_times.append(time.perf_counter() - started)
    baseline_publish_embedding_texts = baseline_embeddings.document_texts

    # Current publisher: first publish embeds all documents; repeated unchanged
    # publishes are deduplicated through the active version manifest.
    current_client = QdrantClient(":memory:")
    current_embeddings = DelayedCountingEmbeddings(delay, query_delay)
    retriever = QdrantMaterialRetriever(documents={"dl": root}, qdrant_path=root / "qdrant")
    retriever._resources = lambda: (current_client, current_embeddings)  # type: ignore[method-assign]
    current_times: list[float] = []
    current_stats: list[dict[str, object]] = []
    for _ in range(args.repeats):
        started = time.perf_counter()
        current_stats.append(retriever.rebuild(book_ids=["dl"])[0])
        current_times.append(time.perf_counter() - started)
    current_publish_embedding_texts = current_embeddings.document_texts

    # Verify the per-book publication lock rejects competing publishers.
    lock = retriever._build_lock("dl")
    assert lock.acquire(blocking=False)
    try:
        try:
            retriever.rebuild(book_ids=["dl"])
        except ConflictError:
            concurrent_publish_rejected = True
        else:
            concurrent_publish_rejected = False
    finally:
        lock.release()

    baseline_query_times: list[float] = []
    baseline_store = QdrantVectorStore(
        client=baseline_client,
        collection_name=f"baseline_{args.repeats - 1}",
        embedding=baseline_embeddings,
    )
    for _ in range(30):
        started = time.perf_counter()
        baseline_store.similarity_search_with_score("What is the core concept?", k=5)
        baseline_query_times.append(time.perf_counter() - started)

    query_times: list[float] = []
    for _ in range(30):
        started = time.perf_counter()
        result = retriever.retrieve(book_id="dl", question="What is the core concept?")
        query_times.append(time.perf_counter() - started)
        assert result.chunks and result.chunks[0].source.index_version

    assert all(stat.get("skipped") for stat in current_stats[1:])
    assert concurrent_publish_rejected
    print("publish_benchmark")
    print(f"documents={args.documents}; repeats={args.repeats}; embedding_delay_ms={args.embedding_delay_ms}; query_delay_ms={args.query_delay_ms}")
    print(f"baseline_publish_embedding_texts={baseline_publish_embedding_texts}; baseline_total_seconds={sum(baseline_times):.3f}")
    print(f"current_publish_embedding_texts={current_publish_embedding_texts}; current_total_seconds={sum(current_times):.3f}")
    print(f"unchanged_publishes_skipped={sum(bool(stat.get('skipped')) for stat in current_stats[1:])}")
    print(f"concurrent_publish_rejected={concurrent_publish_rejected}")
    print(f"baseline_query_p50_ms={statistics.median(baseline_query_times) * 1000:.2f}; baseline_query_p95_ms={percentile(baseline_query_times, 0.95) * 1000:.2f}")
    print(f"current_query_p50_ms={statistics.median(query_times) * 1000:.2f}; current_query_p95_ms={percentile(query_times, 0.95) * 1000:.2f}")
    print(f"workspace={root}")


if __name__ == "__main__":
    main()
