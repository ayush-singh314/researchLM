"""URL ingest for ResearchLM: LangChain `WebBaseLoader` → text chunks for Qdrant.

Used by `load_webpage` callers: `backend.api.ingest.ingest_urls` (POST /sessions/{id}/urls)
and `paper_loader.load_document` when the source starts with http(s).

Not used: PDF figures, GPT-4o captions, PyMuPDF. HTML only.
"""

from __future__ import annotations

# ── Library ──────────────────────────────────────────────────────────────────
# WebBaseLoader lives in langchain_community (not langchain-core).
# Under the hood it: HTTP GET the URL → BeautifulSoup (bs4) strips tags →
# one LangChain Document whose page_content is visible text.
from langchain_community.document_loaders import WebBaseLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Same default window as PDF/text ingest in paper_loader.py (keep in sync).
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    add_start_index=True,
)


def _stamp_title(docs: list[Document], title: str) -> list[Document]:
    """Set metadata.title so the sidebar / delete-by-title can name this URL."""
    for doc in docs:
        doc.metadata["title"] = title
        doc.metadata.setdefault("modality", "text")
        doc.metadata.setdefault("source_type", "web_html")
    return docs


def load_webpage(url: str) -> list[Document]:
    """Fetch one page, chunk it, return Documents ready for `add_paper`."""

    # ── 1. Fetch + parse HTML ───────────────────────────────────────────────
    # requests_kwargs timeout=30: hang on a slow site fails the one URL, not the API.
    # .load() is synchronous (matches FastAPI ingest_urls, which is not async).
    raw_docs = WebBaseLoader(url, requests_kwargs={"timeout": 30}).load()

    # ── 2. Title for Qdrant metadata ────────────────────────────────────────
    # Soup usually puts <title> on docs[0].metadata["title"]; fall back to the URL.
    title = (raw_docs[0].metadata.get("title") or url) if raw_docs else url

    # ── 3. Chunk ────────────────────────────────────────────────────────────
    # RecursiveCharacterTextSplitter: same 1000/200 as default PDF path.
    # No "research" section profile — HTML has no Abstract/Method headers we trust.
    chunks = _splitter.split_documents(raw_docs)

    # ── 4. Stamp + return ───────────────────────────────────────────────────
    # add_paper embeds these into papeer_{session_id}. Empty pages still return [].
    return _stamp_title(chunks, title)
