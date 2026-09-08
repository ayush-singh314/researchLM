"""Extract figures from PDFs with PyMuPDF for multimodal RAG indexing."""

import logging
import re
from pathlib import Path

import fitz

from backend.llm_schemas import ExtractedImage

logger = logging.getLogger(__name__)

EXTRACTED_IMAGES_ROOT = Path("documents/extracted_images")
MIN_WIDTH = 50
MIN_HEIGHT = 50
MIN_BYTES = 1024


def paper_id_from_title(title: str) -> str:
    """Build a stable filesystem-safe id from a paper title."""
    slug = re.sub(r"[^\w\-]+", "_", title.strip().lower()).strip("_")
    return slug[:64] or "paper"


def extract_pdf_images(pdf_path: str, paper_id: str) -> list[ExtractedImage]:
    """
    Extract embedded images from a PDF and save them under
    documents/extracted_images/<paper_id>/.
    """
    out_dir = EXTRACTED_IMAGES_ROOT / paper_id
    out_dir.mkdir(parents=True, exist_ok=True)
    source_pdf = str(Path(pdf_path).resolve())

    extracted: list[ExtractedImage] = []
    seen_xrefs_per_page: dict[int, set[int]] = {}
    image_counter = 0

    doc = fitz.open(pdf_path)
    try:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_number = page_idx + 1
            seen_xrefs = seen_xrefs_per_page.setdefault(page_number, set())

            for img_info in page.get_images(full=True):
                xref = img_info[0]
                if xref in seen_xrefs:
                    continue
                seen_xrefs.add(xref)

                try:
                    base = doc.extract_image(xref)
                except Exception as exc:
                    logger.debug("Skipping xref %s on page %s: %s", xref, page_number, exc)
                    continue

                width = int(base.get("width") or 0)
                height = int(base.get("height") or 0)
                if width < MIN_WIDTH or height < MIN_HEIGHT:
                    continue

                img_bytes = base.get("image") or b""
                if len(img_bytes) < MIN_BYTES:
                    continue

                ext = base.get("ext") or "png"
                image_counter += 1
                filename = f"page_{page_number:04d}_img_{image_counter:02d}.{ext}"
                image_path = out_dir / filename
                image_path.write_bytes(img_bytes)

                extracted.append(
                    ExtractedImage(
                        paper_id=paper_id,
                        page_number=page_number,
                        image_index=image_counter,
                        image_path=str(image_path),
                        source_pdf=source_pdf,
                        xref=xref,
                    )
                )
    finally:
        doc.close()

    logger.info("Extracted %d image(s) from %s", len(extracted), pdf_path)
    return extracted


def extract_scanned_pages(pdf_path: str, paper_id: str, min_text_chars: int = 80) -> list[ExtractedImage]:
    """Rasterize pages that have almost no extractable text (scanned / image PDFs)."""
    out_dir = EXTRACTED_IMAGES_ROOT / paper_id
    out_dir.mkdir(parents=True, exist_ok=True)
    source_pdf = str(Path(pdf_path).resolve())
    extracted: list[ExtractedImage] = []
    doc = fitz.open(pdf_path)
    try:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            page_number = page_idx + 1
            text = (page.get_text("text") or "").strip()
            if len(text) >= min_text_chars:
                continue
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            image_counter = page_number
            filename = f"page_{page_number:04d}_scan.png"
            image_path = out_dir / filename
            pix.save(str(image_path))
            extracted.append(
                ExtractedImage(
                    paper_id=paper_id,
                    page_number=page_number,
                    image_index=image_counter,
                    image_path=str(image_path),
                    source_pdf=source_pdf,
                    xref=0,
                )
            )
    finally:
        doc.close()
    logger.info("Rasterized %d scanned page(s) from %s", len(extracted), pdf_path)
    return extracted


def page_text_map(pdf_path: str) -> dict[int, str]:
    """Return 1-based page number -> page text for caption context."""
    texts: dict[int, str] = {}
    doc = fitz.open(pdf_path)
    try:
        for page_idx in range(len(doc)):
            texts[page_idx + 1] = doc[page_idx].get_text("text")
    finally:
        doc.close()
    return texts
