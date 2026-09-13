"""Turn a PDF, text/markdown file, or URL into LangChain Documents (text chunks + optional figure chunks).

Used by `backend.api.ingest` (chat uploads) and `evaluation.experiment_runner` (eval corpus).
PDFs: PyMuPDF pages → splitter or research chunker → optional GPT-4o captions from extracted images.
"""

import logging
import re
from pathlib import Path

from langchain_community.document_loaders import PyMuPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.rag.image_captioner import generate_image_caption
from backend.llm_schemas import ExtractedImage
from backend.rag.pdf_images import (
    extract_pdf_images,
    extract_scanned_pages,
    page_text_map,
    paper_id_from_title,
)
from backend.rag.chunking import chunk_research_paper_pages
from backend.rag.web_base import load_webpage

logger = logging.getLogger(__name__)

# Default (chat) chunking: 200-char overlap so claims split across a window still retrieve.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, add_start_index=True
)
_md_splitter = RecursiveCharacterTextSplitter.from_language(
    "markdown", chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, add_start_index=True
)


def _stamp_title(docs: list[Document], title: str) -> list[Document]:
    """Set `metadata.title` used later to list/delete papers in Qdrant."""
    for doc in docs:
        doc.metadata["title"] = title
        doc.metadata.setdefault("modality", "text")
        doc.metadata.setdefault("source_type", "pdf_text")
    return docs


def _nearby_page_context(page_texts: dict[int, str], page_number: int, max_chars: int = 500) -> str:
    """Grab nearby body text (skip Figure/Table labels) so the image chunk is searchable with the figure."""
    raw = page_texts.get(page_number, "").strip()
    if not raw:
        return ""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    kept: list[str] = []
    total = 0
    for para in paragraphs:
        if re.match(r"^(?:Figure|Table|Fig\.)\s*\d+", para, re.I):
            continue
        if total + len(para) > max_chars:
            break
        kept.append(para)
        total += len(para)
    return "\n".join(kept)[:max_chars]


def _image_to_document(
    extracted: ExtractedImage,
    caption: str,
    title: str,
    page_texts: dict[int, str] | None = None,
) -> Document:
    """One retrievable chunk: caption + nearby text; `modality=image` (not the pixels)."""
    page = extracted.page_number
    linked = _nearby_page_context(page_texts or {}, page)
    if linked:
        page_content = (
            f"Figure on page {page}.\n"
            f"Nearby explanatory text: {linked}\n\n"
            f"Caption: {caption}"
        )
    else:
        page_content = f"Figure extracted from page {page}: {caption}"
    return Document(
        page_content=page_content,
        metadata={
            "title": title,
            "modality": "image",
            "page_number": page,
            "image_path": extracted.image_path,
            "caption": caption,
            "linked_page_text": linked or None,
            "source_type": "pdf_figure",
            "source_pdf": extracted.source_pdf,
            "paper_id": extracted.paper_id,
            "image_index": extracted.image_index,
        },
    )


def _require_existing_pdf(file_path: str) -> str:
    """Resolve to an absolute path and verify the PDF exists on disk."""
    resolved = Path(file_path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"PDF path does not exist: {resolved}")
    if resolved.stat().st_size == 0:
        raise ValueError(f"PDF file is empty: {resolved}")
    return str(resolved)


def _load_pdf_image_chunks(pdf_path: str, title: str) -> list[Document]:
    """Extract figures, caption with GPT-4o; scanned PDFs fall back to page rasters."""
    paper_id = paper_id_from_title(title)
    try:
        extracted = extract_pdf_images(pdf_path, paper_id)
    except Exception as exc:
        logger.error("Image extraction failed for %s: %s", pdf_path, exc)
        extracted = []

    try:
        page_texts = page_text_map(pdf_path)
    except Exception as exc:
        logger.warning("Could not load page text for caption context: %s", exc)
        page_texts = {}

    # Little/no extractable text → treat pages as images (scanned PDF).
    text_len = sum(len((t or "").strip()) for t in page_texts.values())
    if text_len < 80:
        try:
            extracted = extract_scanned_pages(pdf_path, paper_id)
        except Exception as exc:
            logger.error("Scanned-page raster failed for %s: %s", pdf_path, exc)

    if not extracted:
        return []

    image_docs: list[Document] = []
    for img in extracted:
        try:
            context = page_texts.get(img.page_number, "")[:800]
            caption = generate_image_caption(
                img.image_path,
                page_number=img.page_number,
                context_text=context or None,
            )
            image_docs.append(_image_to_document(img, caption, title, page_texts=page_texts))
            logger.info(
                "Indexed image chunk for %s page %s (%s)",
                title,
                img.page_number,
                img.image_path,
            )
        except Exception as exc:
            logger.warning(
                "Caption failed for %s page %s (%s): %s",
                title,
                img.page_number,
                img.image_path,
                exc,
            )
            # Still index a stub so the figure page exists in the vector store.
            image_docs.append(
                _image_to_document(
                    img,
                    f"Scanned or extracted page {img.page_number} of {title}.",
                    title,
                    page_texts=page_texts,
                )
            )

    logger.info(
        "Image ingestion for %s: %d/%d captioned",
        title,
        len(image_docs),
        len(extracted),
    )
    return image_docs


def load_pdf(
    file_path: str,
    paper_title: str | None = None,
    include_images: bool = True,
    chunking_profile: str = "default",
) -> list[Document]:
    """Load a PDF: default 1000/200 chunks, or `research` section-aware; optionally append image chunks."""
    resolved_path = _require_existing_pdf(file_path)
    title = paper_title or Path(resolved_path).stem
    raw_docs = PyMuPDFLoader(resolved_path).load()
    if chunking_profile == "research":
        text_docs = _stamp_title(chunk_research_paper_pages(raw_docs), title)
    else:
        text_docs = _stamp_title(_splitter.split_documents(raw_docs), title)
    image_docs = _load_pdf_image_chunks(resolved_path, title) if include_images else []
    docs = [doc for doc in (text_docs + image_docs) if (doc.page_content or "").strip()]
    return docs


def load_text(file_path: str) -> list[Document]:
    """UTF-8 .txt → default character splitter."""
    docs = TextLoader(file_path, encoding="utf-8").load()
    return _stamp_title(_splitter.split_documents(docs), Path(file_path).stem)


def load_markdown(file_path: str) -> list[Document]:
    """Markdown-aware splitter so headings stay with their sections."""
    docs = TextLoader(file_path, encoding="utf-8").load()
    return _stamp_title(_md_splitter.split_documents(docs), Path(file_path).stem)


def load_document(
    source: str,
    paper_title: str | None = None,
    include_images: bool = True,
    chunking_profile: str = "default",
) -> list[Document]:
    """Dispatch by URL scheme or file extension; eval uses `include_images=False` for text_only."""
    if source.startswith(("http://", "https://")):
        return load_webpage(source)
    ext = Path(source).suffix.lower()
    if ext == ".pdf":
        return load_pdf(
            source,
            paper_title=paper_title,
            include_images=include_images,
            chunking_profile=chunking_profile,
        )
    if ext == ".txt":
        return load_text(source)
    if ext in (".md", ".markdown"):
        return load_markdown(source)
    raise ValueError(f"Unsupported file type: {ext}")
