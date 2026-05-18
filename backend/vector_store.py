import logging
import os

from dotenv import load_dotenv
from langchain_classic.embeddings import CacheBackedEmbeddings
from langchain_classic.storage import LocalFileStore
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from backend.hybrid_retrieval import bm25_retrieve, reciprocal_rank_fusion

load_dotenv()

logger = logging.getLogger(__name__)

# In-memory corpus cache for BM25 (invalidated on add_paper).
_session_corpus_cache: dict[str, list[Document]] = {}

# ── Config ───────────────────────────────────────────────────────────────────

EMBEDDING_DIM = 1536  # text-embedding-3-small

# ── Singletons ────────────────────────────────────────────────────────────────

base_embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
embedding_file_store = LocalFileStore("./embedding_cache/")
embeddings = CacheBackedEmbeddings.from_bytes_store(
    base_embeddings,
    embedding_file_store,
    namespace=base_embeddings.model,
    query_embedding_cache=True,
    key_encoder="blake2b",
)

qdrant_client = QdrantClient(
    url=os.environ["QDRANT_URL"],
    api_key=os.environ["QDRANT_API_KEY"],
    timeout=120,
)


# ── Collection ───────────────────────────────────────────────────────────────

def get_collection_name(session_id: str) -> str:
    return f"papeer_{session_id.replace('-', '_')}"


def get_vectorstore(session_id: str) -> QdrantVectorStore:
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


# ── Public API ───────────────────────────────────────────────────────────────

def _ensure_chunk_metadata(doc: Document) -> Document:
    """Ensure text chunks have modality metadata; image chunks are set at ingestion."""
    doc.metadata.setdefault("modality", "text")
    return doc


def _invalidate_corpus_cache(session_id: str) -> None:
    _session_corpus_cache.pop(session_id, None)


def _scroll_session_documents(session_id: str) -> list[Document]:
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
    if session_id not in _session_corpus_cache:
        _session_corpus_cache[session_id] = _scroll_session_documents(session_id)
    return _session_corpus_cache[session_id]


def add_paper(docs: list[Document], session_id: str) -> None:
    """Index text and image-caption chunks in the session vector store."""
    if not docs:
        return
    normalized = [_ensure_chunk_metadata(doc) for doc in docs]
    get_vectorstore(session_id).add_documents(normalized)
    _invalidate_corpus_cache(session_id)


def list_papers(session_id: str) -> list[str]:
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


def search(
    query: str,
    session_id: str,
    k: int = 4,
    strategy: str | None = None,
) -> list[Document]:
    """
    Retrieve chunks for a session.

    strategy: "dense" (default) or "hybrid" (BM25 + dense via RRF).
    Falls back to RETRIEVAL_STRATEGY env var when strategy is None.
    """
    chosen = (strategy or os.environ.get("RETRIEVAL_STRATEGY", "dense")).lower().strip()

    if chosen == "dense":
        return get_vectorstore(session_id).similarity_search(query, k=k)

    if chosen == "hybrid":
        logger.info("Retrieval strategy=hybrid session=%s top_k=%d", session_id, k)
        store = get_vectorstore(session_id)
        dense_docs = store.similarity_search(query, k=k * 2)
        corpus = _get_session_corpus(session_id)
        bm25_docs = bm25_retrieve(query, corpus, k=k * 2)
        return reciprocal_rank_fusion([dense_docs, bm25_docs], k=k)

    logger.warning("Unknown retrieval strategy '%s'; using dense", chosen)
    return get_vectorstore(session_id).similarity_search(query, k=k)
