"""Per-session Qdrant index for chat RAG: embed, add/list/delete papers, hybrid or dense search.

Used by `backend.api.ingest` (writes) and `backend.rag.graph` retrieve tool (reads).
Eval uses `evaluation.vector_index.EvalVectorIndex` instead — a separate collection namespace.
Isolation is the collection name `papeer_{session_id}`, not a metadata filter.
Default retrieve: 0.9/0.1 weighted RRF then MiniLM cross-encoder, then top-k.
"""

import logging
import os

from dotenv import load_dotenv
from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_community.storage import RedisStore
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, FieldCondition, Filter, MatchValue, VectorParams

from backend.rag.hybrid_retrieval import bm25_retrieve, reciprocal_rank_fusion
from backend.rag.rerank import postprocess_retrieved, use_cross_encoder

load_dotenv()
os.environ.setdefault("USER_AGENT", "ResearchLM/0.1")

logger = logging.getLogger(__name__)

# BM25 needs the full session corpus in RAM; drop on add/delete so it cannot go stale.
_session_corpus_cache: dict[str, list[Document]] = {}

EMBEDDING_DIM = 1536  # must match text-embedding-3-small or Qdrant insert fails


def _embedding_byte_store() -> RedisStore:
    """Redis Cloud byte store for CacheBackedEmbeddings. No LocalFileStore fallback."""
    redis_url = (os.environ.get("REDIS_URL") or "").strip()
    if not redis_url:
        raise RuntimeError(
            "REDIS_URL is required for the embedding cache. "
            "Set it to your Redis Cloud connection URL (rediss://...)."
        )
    try:
        import redis
    except ImportError as exc:
        raise RuntimeError(
            "The redis package is required for the embedding cache."
        ) from exc

    try:
        client = redis.Redis.from_url(
            redis_url,
            decode_responses=False,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        client.ping()
    except redis.exceptions.RedisError as exc:
        raise RuntimeError(
            "Could not connect to Redis for the embedding cache. "
            "Check REDIS_URL and Redis Cloud status."
        ) from exc

    return RedisStore(client=client, ttl=None, namespace="researchlm_embed")


base_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
# Same query/chunk twice → Redis cache, not another OpenAI embed call.
embeddings = CacheBackedEmbeddings.from_bytes_store(
    base_embeddings,
    _embedding_byte_store(),
    namespace=base_embeddings.model,
    query_embedding_cache=True,
    key_encoder="blake2b",
)

qdrant_client = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ["QDRANT_API_KEY"],
    timeout=120,
    check_compatibility=False,
)


def get_collection_name(session_id: str) -> str:
    """Map session UUID → Qdrant collection; hyphens become underscores (Qdrant name rules)."""
    return f"papeer_{session_id.replace('-', '_')}"


def get_vectorstore(session_id: str) -> QdrantVectorStore:
    """Get or create this session's collection (cosine, dim 1536) and wrap it for LangChain."""
    collection_name = get_collection_name(session_id)
    if not qdrant_client.collection_exists(collection_name):
        qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )
    return QdrantVectorStore(
        client=qdrant_client,
        collection_name=collection_name,
        embedding=embeddings,
    )


def _ensure_chunk_metadata(doc: Document) -> Document:
    """Default modality to text; image chunks already set this at ingest."""
    doc.metadata.setdefault("modality", "text")
    return doc


def _invalidate_corpus_cache(session_id: str) -> None:
    """Clear BM25 cache after the collection changes."""
    _session_corpus_cache.pop(session_id, None)


def _scroll_session_documents(session_id: str) -> list[Document]:
    """Read every point's payload — required to build a BM25 corpus (Qdrant is vectors-only)."""
    collection_name = get_collection_name(session_id)
    if not qdrant_client.collection_exists(collection_name):
        return []
    docs: list[Document] = []
    offset = None
    while True:
        points, offset = qdrant_client.scroll(
            collection_name=collection_name,
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


def _get_session_corpus(session_id: str) -> list[Document]:
    """Cached full-collection scroll for hybrid BM25."""
    if session_id not in _session_corpus_cache:
        _session_corpus_cache[session_id] = _scroll_session_documents(session_id)
    return _session_corpus_cache[session_id]


def add_paper(docs: list[Document], session_id: str) -> None:
    """Embed and upsert chunks into this session only; then refresh BM25 cache."""
    if not docs:
        return
    normalized = [_ensure_chunk_metadata(doc) for doc in docs]
    get_vectorstore(session_id).add_documents(normalized)
    _invalidate_corpus_cache(session_id)


def list_papers(session_id: str) -> list[str]:
    """Unique `metadata.title` values for the documents sidebar."""
    collection_name = get_collection_name(session_id)
    if not qdrant_client.collection_exists(collection_name):
        return []
    seen: set[str] = set()
    titles: list[str] = []
    offset = None
    while True:
        points, offset = qdrant_client.scroll(
            collection_name=collection_name,
            with_payload=True,
            limit=100,
            offset=offset,
        )
        for point in points:
            title = (point.payload or {}).get("metadata", {}).get("title")
            if title and title not in seen:
                seen.add(title)
                titles.append(title)
        if offset is None:
            break
    return titles


def delete_paper(session_id: str, title: str) -> None:
    """Delete by payload filter on title — chunks, not the whole collection."""
    collection_name = get_collection_name(session_id)
    if not qdrant_client.collection_exists(collection_name):
        return
    qdrant_client.delete(
        collection_name=collection_name,
        points_selector=Filter(
            must=[FieldCondition(key="metadata.title", match=MatchValue(value=title))]
        ),
    )
    _invalidate_corpus_cache(session_id)


def _rrf_weights() -> list[float]:
    """Chat hybrid mix; defaults match production 90% dense / 10% BM25."""
    dense = float(os.environ.get("RRF_DENSE_WEIGHT", "0.9"))
    bm25 = float(os.environ.get("RRF_BM25_WEIGHT", "0.1"))
    return [dense, bm25]


def search(
    query: str,
    session_id: str,
    k: int = 4,
    strategy: str | None = None,
) -> list[Document]:
    """Chat retrieval: hybrid RRF (0.9/0.1) then optional cross-encoder; dense is cosine-only."""
    chosen = (strategy or os.environ.get("RETRIEVAL_STRATEGY", "hybrid")).lower().strip()

    if chosen == "dense":
        return get_vectorstore(session_id).similarity_search(query, k=k)

    if chosen == "hybrid":
        weights = _rrf_weights()
        rerank = use_cross_encoder()
        # Same over-fetch as eval StrategyRetriever when CE is on.
        fetch_k = max(k * 3, k + 10) if rerank else k
        # Same inner candidate pool as evaluation.vector_index.hybrid_search.
        candidate_k = max(fetch_k * 3, 40)
        logger.info(
            "Retrieval strategy=hybrid session=%s top_k=%d fetch_k=%d candidate_k=%d "
            "rrf_dense=%.2f rrf_bm25=%.2f cross_encoder=%s",
            session_id,
            k,
            fetch_k,
            candidate_k,
            weights[0],
            weights[1],
            rerank,
        )
        store = get_vectorstore(session_id)
        dense_docs = store.similarity_search(query, k=candidate_k)
        corpus = _get_session_corpus(session_id)
        bm25_docs = bm25_retrieve(query, corpus, k=candidate_k)
        fused = reciprocal_rank_fusion(
            [dense_docs, bm25_docs],
            k=fetch_k,
            weights=weights,
        )
        if rerank:
            return postprocess_retrieved(query, fused, top_k=k)
        return fused[:k]

    logger.warning("Unknown retrieval strategy '%s'; using dense", chosen)
    return get_vectorstore(session_id).similarity_search(query, k=k)
