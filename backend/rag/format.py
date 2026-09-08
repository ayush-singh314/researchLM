"""Format retrieved text and image-caption chunks for downstream LLM prompts."""

from langchain_core.documents import Document


def format_retrieved_chunk(doc: Document) -> str:
    """Format a single chunk with modality-aware labels."""
    meta = doc.metadata or {}
    modality = meta.get("modality", "text")

    if modality == "image":
        page = meta.get("page_number", "?")
        title = meta.get("title", "unknown paper")
        caption = meta.get("caption") or doc.page_content
        return f"[Figure | page {page} | {title}]\nCaption: {caption}"

    page = meta.get("page") or meta.get("page_number")
    title = meta.get("title")
    prefix = "[Text"
    if page is not None:
        prefix += f" | page {page}"
    if title:
        prefix += f" | {title}"
    prefix += "] "
    return prefix + doc.page_content


def format_retrieved_context(docs: list[Document]) -> str:
    """Join retrieved chunks into a single evidence block."""
    if not docs:
        return ""
    return "\n\n---\n\n".join(format_retrieved_chunk(doc) for doc in docs)
