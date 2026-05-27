"""Post-retrieval deduplication and lightweight reranking for evaluation."""

from __future__ import annotations

import re

from langchain_core.documents import Document

from backend.hybrid_retrieval import chunk_key

_TOKEN_RE = re.compile(r"\w+")
_FIGURE_QUERY_RE = re.compile(r"\b(figure|fig\.|table|chart|diagram|plot|architecture)\b", re.I)


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def deduplicate_documents(docs: list[Document]) -> list[Document]:
    """Remove duplicate chunks by stable chunk key."""
    unique: dict[str, Document] = {}
    for doc in docs:
        unique.setdefault(chunk_key(doc), doc)
    return list(unique.values())


def rerank_documents(query: str, docs: list[Document]) -> list[Document]:
    """
    Lightweight lexical reranker (no extra model calls).
    Boosts figure/table chunks when the query references visuals.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return docs

    wants_visual = bool(_FIGURE_QUERY_RE.search(query))

    def score(item: tuple[int, Document]) -> float:
        idx, doc = item
        doc_tokens = _tokenize(doc.page_content)
        overlap = len(query_tokens & doc_tokens) / len(query_tokens)
        meta = doc.metadata or {}
        bonus = 0.0
        if wants_visual and meta.get("modality") == "image":
            bonus += 0.12
        if meta.get("contains_figure_ref"):
            bonus += 0.06
        if meta.get("linked_page_text"):
            bonus += 0.04
        return overlap + bonus - (idx * 1e-4)

    ranked = sorted(enumerate(docs), key=score, reverse=True)
    return [doc for _, doc in ranked]


def postprocess_retrieved(
    query: str,
    docs: list[Document],
    *,
    top_k: int,
) -> list[Document]:
    """Deduplicate, rerank, and trim to top_k."""
    if not docs:
        return []
    cleaned = deduplicate_documents(docs)
    ranked = rerank_documents(query, cleaned)
    return ranked[:top_k]
