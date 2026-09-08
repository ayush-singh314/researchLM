import os
import tempfile
from pathlib import Path

from backend.rag.paper_loader import load_document, load_webpage
from backend.rag.vector_store import add_paper


def persist_upload_bytes(filename: str, payload: bytes) -> Path:
    suffix = Path(filename).suffix.lower() or ".bin"
    if not payload:
        raise ValueError(f"Uploaded file has no content: {filename}")
    with tempfile.NamedTemporaryFile(
        delete=False, suffix=suffix, prefix="researchlm_upload_"
    ) as tmp:
        tmp.write(payload)
        tmp.flush()
        os.fsync(tmp.fileno())
        saved_path = Path(tmp.name)
    resolved = saved_path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Saved upload not found at resolved path: {resolved}")
    return resolved


def ingest_upload(session_id: str, filename: str, payload: bytes) -> str:
    saved_path = persist_upload_bytes(filename, payload)
    try:
        docs = load_document(str(saved_path), paper_title=Path(filename).stem)
        if not docs:
            raise ValueError(
                f"Could not extract text or pages from {filename}. "
                "The file may be empty, encrypted, or unreadable."
            )
        add_paper(docs, session_id)
        return Path(filename).stem
    finally:
        if saved_path.is_file():
            saved_path.unlink(missing_ok=True)


def ingest_urls(session_id: str, urls: list[str]) -> tuple[list[str], list[str]]:
    added: list[str] = []
    errors: list[str] = []
    for url in urls:
        try:
            docs = load_webpage(url)
            add_paper(docs, session_id)
            title = (docs[0].metadata.get("title") if docs else url) or url
            added.append(str(title)[:200])
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    return added, errors
