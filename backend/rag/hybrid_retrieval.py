"""BM25 retrieval and reciprocal rank fusion for hybrid search."""

from __future__ import annotations

import re

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

_TOKEN_RE = re.compile(r"\w+")
RRF_K = 60


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def chunk_key(doc: Document) -> str:
    """Stable deduplication key for a chunk."""
    meta = doc.metadata or {}
    title = meta.get("title", "")
    if meta.get("modality") == "image":
        return f"{title}:image:{meta.get('page_number')}:{meta.get('image_index')}"
    start = meta.get("start_index")
    if start is not None:
        return f"{title}:text:{start}"
    return doc.page_content[:500]


def reciprocal_rank_fusion(ranked_lists: list[list[Document]], k: int = 4) -> list[Document]:
    """Fuse multiple ranked lists with RRF and return top_k documents."""
    fused: dict[str, tuple[float, Document]] = {}
    for docs in ranked_lists:
        for rank, doc in enumerate(docs):
            key = chunk_key(doc)
            prev_score, existing = fused.get(key, (0.0, doc))
            fused[key] = (prev_score + 1.0 / (RRF_K + rank + 1), existing)
    ranked = sorted(fused.values(), key=lambda item: item[0], reverse=True)
    return [doc for _, doc in ranked[:k]]


def bm25_retrieve(query: str, corpus: list[Document], k: int) -> list[Document]:
    """Return top-k documents from a corpus using BM25."""
    if not corpus or k <= 0:
        return []
    tokenized_corpus = [_tokenize(doc.page_content) for doc in corpus]
    if not any(tokenized_corpus):
        return []
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(enumerate(scores), key=lambda item: item[1], reverse=True)
    return [corpus[i] for i, score in ranked[:k] if score > 0]
