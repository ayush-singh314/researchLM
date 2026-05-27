import logging
import re
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from langchain_community.document_loaders import PyMuPDFLoader, TextLoader, WebBaseLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.image_captioner import generate_image_caption
from backend.models import ExtractedImage
from backend.pdf_images import extract_pdf_images, page_text_map, paper_id_from_title
from backend.research_chunking import chunk_research_paper_pages

logger = logging.getLogger(__name__)

_ARXIV_ID_RE = re.compile(r"(\d{4}\.\d{4,5}(?:v\d+)?)")

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, add_start_index=True
)
_md_splitter = RecursiveCharacterTextSplitter.from_language(
    "markdown", chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP, add_start_index=True
)


def _stamp_title(docs: list[Document], title: str) -> list[Document]:
    for doc in docs:
        doc.metadata["title"] = title
        doc.metadata.setdefault("modality", "text")
        doc.metadata.setdefault("source_type", "pdf_text")
    return docs


def _nearby_page_context(page_texts: dict[int, str], page_number: int, max_chars: int = 500) -> str:
    """Return explanatory text near a figure on the same page."""
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
    """Build a LangChain Document for an image-caption chunk."""
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
    """Extract PDF figures, caption them, and return retrievable image chunks."""
    paper_id = paper_id_from_title(title)
    try:
        extracted = extract_pdf_images(pdf_path, paper_id)
    except Exception as exc:
        logger.error("Image extraction failed for %s: %s", pdf_path, exc)
        return []

    if not extracted:
        return []

    try:
        page_texts = page_text_map(pdf_path)
    except Exception as exc:
        logger.warning("Could not load page text for caption context: %s", exc)
        page_texts = {}

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
    resolved_path = _require_existing_pdf(file_path)
    title = paper_title or Path(resolved_path).stem
    raw_docs = PyMuPDFLoader(resolved_path).load()
    if chunking_profile == "research":
        text_docs = _stamp_title(chunk_research_paper_pages(raw_docs), title)
    else:
        text_docs = _stamp_title(_splitter.split_documents(raw_docs), title)
    image_docs = _load_pdf_image_chunks(resolved_path, title) if include_images else []
    return text_docs + image_docs


def load_text(file_path: str) -> list[Document]:
    docs = TextLoader(file_path, encoding="utf-8").load()
    return _stamp_title(_splitter.split_documents(docs), Path(file_path).stem)


def load_markdown(file_path: str) -> list[Document]:
    docs = TextLoader(file_path, encoding="utf-8").load()
    return _stamp_title(_md_splitter.split_documents(docs), Path(file_path).stem)


def load_webpage(url: str) -> list[Document]:
    docs = WebBaseLoader(url, requests_kwargs={"timeout": 30}).load()
    title = (docs[0].metadata.get("title") or url) if docs else url
    return _stamp_title(_splitter.split_documents(docs), title)


def _extract_arxiv_id(query: str) -> str | None:
    """Return bare ArXiv ID (no version suffix) if one appears in the query."""
    m = _ARXIV_ID_RE.search(query)
    if m:
        return re.sub(r"v\d+$", "", m.group(1))
    return None


def _arxiv_api_lookup(arxiv_id: str) -> str:
    """Fetch paper title by ID from the ArXiv Atom API."""
    url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"
    with urllib.request.urlopen(url, timeout=10) as resp:
        xml = resp.read().decode()
    titles = re.findall(r"<title>(.*?)</title>", xml, re.DOTALL)
    return titles[1].strip() if len(titles) > 1 else arxiv_id


def _arxiv_search(query: str) -> str:
    """Search ArXiv Atom API by title phrase and return the top result's bare paper ID."""
    phrase = query.strip('"')
    search_query = urllib.parse.quote(f'ti:"{phrase}"')
    url = f"https://export.arxiv.org/api/query?search_query={search_query}&max_results=1&sortBy=relevance"
    with urllib.request.urlopen(url, timeout=15) as resp:
        xml = resp.read().decode()
    m = re.search(r"<id>https?://arxiv\.org/abs/(\d{4}\.\d{4,5}(?:v\d+)?)</id>", xml)
    if not m:
        raise ValueError(f"No ArXiv paper found for: {query}")
    return re.sub(r"v\d+$", "", m.group(1))


def _load_arxiv_by_id(arxiv_id: str) -> list[Document]:
    """Download and chunk an ArXiv paper PDF by its bare ID."""
    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
    with urllib.request.urlopen(pdf_url, timeout=60) as resp:
        pdf_bytes = resp.read()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
        preview = PyMuPDFLoader(tmp_path).load()
        title = (preview[0].metadata.get("title") or "").strip() if preview else ""
        title = title or _arxiv_api_lookup(arxiv_id)
        return load_pdf(tmp_path, paper_title=title)
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def load_arxiv(query: str) -> list[Document]:
    arxiv_id = _extract_arxiv_id(query) or _arxiv_search(query)
    return _load_arxiv_by_id(arxiv_id)


def load_document(
    source: str,
    paper_title: str | None = None,
    include_images: bool = True,
    chunking_profile: str = "default",
) -> list[Document]:
    """Dispatch to the appropriate loader based on URL prefix or file extension."""
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
