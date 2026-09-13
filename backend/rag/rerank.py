"""Cross-encoder rerank shared by chat RAG and the eval CLI.

Scores query–chunk pairs with `cross-encoder/ms-marco-MiniLM-L-6-v2` (override
`CROSS_ENCODER_MODEL`). Used after hybrid RRF (or a dense candidate list), before
trimming to top-k.
"""

from __future__ import annotations

import logging
import os
import threading

from langchain_core.documents import Document

from backend.rag.hybrid_retrieval import chunk_key

logger = logging.getLogger(__name__)

DEFAULT_CROSS_ENCODER = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_MAX_PASSAGE_CHARS = 2000

_cross_encoder = None
_cross_encoder_lock = threading.Lock()


def deduplicate_documents(docs: list[Document]) -> list[Document]:
    """Drop duplicate chunks using the same key as RRF fusion."""
    unique: dict[str, Document] = {}
    for doc in docs:
        unique.setdefault(chunk_key(doc), doc)
    return list(unique.values())


def _get_cross_encoder():
    """Load MiniLM once per process (first chat/eval retrieve may download weights)."""
    global _cross_encoder
    if _cross_encoder is not None:
        return _cross_encoder
    with _cross_encoder_lock:
        if _cross_encoder is not None:
            return _cross_encoder
        from sentence_transformers import CrossEncoder

        model_name = os.environ.get("CROSS_ENCODER_MODEL", DEFAULT_CROSS_ENCODER).strip()
        logger.info("Loading cross-encoder model=%s", model_name)
        _cross_encoder = CrossEncoder(model_name)
        return _cross_encoder


def rerank_documents(query: str, docs: list[Document]) -> list[Document]:
    """Sort candidates by cross-encoder score, highest first."""
    if len(docs) <= 1:
        return docs
    model = _get_cross_encoder()
    pairs = [(query, (doc.page_content or "")[:_MAX_PASSAGE_CHARS]) for doc in docs]
    scores = model.predict(pairs, show_progress_bar=False)
    ranked = sorted(zip(scores, docs, strict=True), key=lambda item: float(item[0]), reverse=True)
    return [doc for _, doc in ranked]


def postprocess_retrieved(
    query: str,
    docs: list[Document],
    *,
    top_k: int,
) -> list[Document]:
    """Dedupe → cross-encoder rerank → keep top_k (eval + chat hybrid)."""
    if not docs:
        return []
    cleaned = deduplicate_documents(docs)
    ranked = rerank_documents(query, cleaned)
    return ranked[:top_k]


def use_cross_encoder() -> bool:
    """Chat/eval can disable rerank with USE_CROSS_ENCODER=false."""
    raw = os.environ.get("USE_CROSS_ENCODER", "true").lower().strip()
    return raw not in ("0", "false", "no", "off")
