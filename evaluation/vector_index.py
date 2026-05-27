"""Evaluation-scoped Qdrant indexing with configurable embedding models."""

from __future__ import annotations

import re

from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_classic.storage import LocalFileStore
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client.models import Distance, VectorParams
from rank_bm25 import BM25Okapi

from backend.hybrid_retrieval import bm25_retrieve, reciprocal_rank_fusion
from backend.vector_store import qdrant_client

EMBEDDING_DIMS: dict[str, int] = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

_TOKEN_RE = re.compile(r"\w+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _embedding_dim(model: str) -> int:
    if model in EMBEDDING_DIMS:
        return EMBEDDING_DIMS[model]
    raise ValueError(
        f"Unknown embedding model '{model}'. Known dims: {list(EMBEDDING_DIMS.keys())}"
    )


def _build_embeddings(model: str) -> CacheBackedEmbeddings:
    base = OpenAIEmbeddings(model=model)
    store = LocalFileStore(f"./embedding_cache/eval_{model.replace('/', '_')}/")
    return CacheBackedEmbeddings.from_bytes_store(
        base,
        store,
        namespace=model,
        query_embedding_cache=True,
        key_encoder="blake2b",
    )


class EvalVectorIndex:
    """Per-experiment vector index with pluggable retrieval strategies."""

    def __init__(self, session_id: str, embedding_model: str):
        self.session_id = session_id
        self.embedding_model = embedding_model
        self.collection_name = f"eval_{session_id.replace('-', '_')}_{embedding_model.replace('-', '_')}"
        self._embeddings = _build_embeddings(embedding_model)
        self._dim = _embedding_dim(embedding_model)
        self._vectorstore: QdrantVectorStore | None = None
        self._bm25: BM25Okapi | None = None
        self._bm25_docs: list[Document] = []

    def _ensure_collection(self) -> QdrantVectorStore:
        if self._vectorstore is not None:
            return self._vectorstore
        if not qdrant_client.collection_exists(self.collection_name):
            qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE),
            )
        self._vectorstore = QdrantVectorStore(
            client=qdrant_client,
            collection_name=self.collection_name,
            embedding=self._embeddings,
        )
        return self._vectorstore

    def index_documents(self, docs: list[Document]) -> None:
        if not docs:
            return
        for doc in docs:
            doc.metadata.setdefault("modality", "text")
        store = self._ensure_collection()
        store.add_documents(docs)
        self._refresh_bm25_corpus()

    def _refresh_bm25_corpus(self) -> None:
        self._bm25_docs = self._scroll_all_documents()
        tokenized = [_tokenize(d.page_content) for d in self._bm25_docs]
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    def _scroll_all_documents(self) -> list[Document]:
        if not qdrant_client.collection_exists(self.collection_name):
            return []
        docs: list[Document] = []
        offset = None
        while True:
            points, offset = qdrant_client.scroll(
                collection_name=self.collection_name,
                with_payload=True,
                limit=200,
                offset=offset,
            )
            for point in points:
                payload = point.payload or {}
                docs.append(
                    Document(
                        page_content=payload.get("page_content", ""),
                        metadata=payload.get("metadata", {}),
                    )
                )
            if offset is None:
                break
        return docs

    def dense_search(self, query: str, k: int = 4) -> list[Document]:
        store = self._ensure_collection()
        return store.similarity_search(query, k=k)

    def keyword_search(self, query: str, k: int = 4) -> list[Document]:
        query_tokens = set(_tokenize(query))
        if not query_tokens:
            return []
        scored: list[tuple[float, Document]] = []
        for doc in self._bm25_docs or self._scroll_all_documents():
            doc_tokens = set(_tokenize(doc.page_content))
            overlap = len(query_tokens & doc_tokens)
            if overlap:
                scored.append((overlap / len(query_tokens), doc))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [doc for _, doc in scored[:k]]

    def bm25_search(self, query: str, k: int = 4) -> list[Document]:
        if self._bm25 is None:
            self._refresh_bm25_corpus()
        if not self._bm25 or not self._bm25_docs:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
        return [self._bm25_docs[i] for i, score in ranked[:k] if score > 0]

    def hybrid_search(self, query: str, k: int = 4) -> list[Document]:
        """Reciprocal rank fusion of BM25 and dense results."""
        candidate_k = max(k * 3, 40)
        dense_docs = self.dense_search(query, k=candidate_k)
        corpus = self._bm25_docs or self._scroll_all_documents()
        bm25_docs = bm25_retrieve(query, corpus, k=candidate_k)
        return reciprocal_rank_fusion([dense_docs, bm25_docs], k=k)
