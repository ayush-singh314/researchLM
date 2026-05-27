"""Section-aware chunking for research PDFs."""

from __future__ import annotations

import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

_SECTION_HEADER_RE = re.compile(
    r"^(?:\d{1,2}(?:\.\d+)*\s+[A-Z]|Abstract|Introduction|Background|"
    r"Model|Experiments|Results|Conclusion|References|Appendix)\b",
    re.MULTILINE,
)
_FIGURE_TABLE_LINE_RE = re.compile(r"^(?:Figure|Table|Fig\.)\s*\d+", re.IGNORECASE)

RESEARCH_CHUNK_SIZE = 1400
RESEARCH_CHUNK_OVERLAP = 120

_research_splitter = RecursiveCharacterTextSplitter(
    chunk_size=RESEARCH_CHUNK_SIZE,
    chunk_overlap=RESEARCH_CHUNK_OVERLAP,
    separators=["\n\n", "\n", ". ", " ", ""],
    add_start_index=True,
)


def _split_page_into_sections(text: str) -> list[str]:
    """Split page text on section headers while keeping figure/table lines attached."""
    if not text.strip():
        return []
    lines = text.splitlines()
    sections: list[str] = []
    current: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                current.append("")
            continue
        is_header = bool(_SECTION_HEADER_RE.match(stripped)) and len(stripped) < 120
        if is_header and current:
            block = "\n".join(current).strip()
            if block:
                sections.append(block)
            current = [stripped]
        else:
            current.append(stripped)

    if current:
        block = "\n".join(current).strip()
        if block:
            sections.append(block)
    return sections if sections else [text.strip()]


def chunk_research_paper_pages(pages: list[Document]) -> list[Document]:
    """Chunk research PDF pages with section boundaries preserved."""
    section_docs: list[Document] = []
    for page_doc in pages:
        page_num = page_doc.metadata.get("page", page_doc.metadata.get("page_number"))
        for section_text in _split_page_into_sections(page_doc.page_content):
            meta = dict(page_doc.metadata)
            meta["page_number"] = page_num
            if _FIGURE_TABLE_LINE_RE.match(section_text.strip()[:80]):
                meta["contains_figure_ref"] = True
            section_docs.append(Document(page_content=section_text, metadata=meta))
    return _research_splitter.split_documents(section_docs)
