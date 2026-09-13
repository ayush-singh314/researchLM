"""HTTP ingest routes: upload files, paste URLs, list/delete papers for a session.

Used by the React workspace (documents pane). Every handler calls
`require_owned_session` first so JWT `sub` must own the session. Bytes/URLs then
go to `backend.api.ingest`, which writes Qdrant — not Postgres.
"""

import uuid

from fastapi import APIRouter, Depends, File, UploadFile

from backend.api.deps import CurrentUser, DbSession, get_current_user, require_owned_session
from backend.api.ingest import ingest_upload, ingest_urls
from backend.api.schemas import DocumentListOut, IngestResult, UrlsIn
from backend.rag.vector_store import delete_paper, list_papers

# JWT required on the whole router; session tenancy is checked per handler.
router = APIRouter(prefix="/sessions", tags=["ingest"], dependencies=[Depends(get_current_user)])

ALLOWED_SUFFIXES = {".pdf", ".txt", ".md", ".markdown"}


@router.post("/{session_id}/documents", response_model=IngestResult)
async def upload_documents(
    session_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    files: list[UploadFile] = File(...),
):
    """POST multipart files into this session's Qdrant collection; partial failures go in `errors`."""
    require_owned_session(db, session_id, user)
    added: list[str] = []
    errors: list[str] = []
    sid = str(session_id)
    for upload in files:
        name = upload.filename or "upload.bin"
        suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        if suffix not in ALLOWED_SUFFIXES:
            errors.append(f"{name}: unsupported type")
            continue
        try:
            payload = await upload.read()
            title = ingest_upload(sid, name, payload)
            added.append(title)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    # 200 even if some files failed — client shows added vs errors.
    return IngestResult(added=added, errors=errors)


@router.post("/{session_id}/urls", response_model=IngestResult)
def load_urls(session_id: uuid.UUID, body: UrlsIn, db: DbSession, user: CurrentUser):
    """POST a list of URLs; each page is fetched, chunked, and indexed like an upload."""
    require_owned_session(db, session_id, user) # does this session exist and does it belongs to the user before index
    added, errors = ingest_urls(str(session_id), body.urls)
    return IngestResult(added=added, errors=errors)


@router.get("/{session_id}/documents", response_model=DocumentListOut)
def get_documents(session_id: uuid.UUID, db: DbSession, user: CurrentUser):
    """List unique paper titles stored in this session's Qdrant collection."""
    require_owned_session(db, session_id, user)
    try:
        titles = list_papers(str(session_id))
    except Exception:
        titles = []  # missing collection / Qdrant down → empty list, not 500
    return DocumentListOut(titles=titles)


@router.delete("/{session_id}/documents", status_code=204)
def remove_document(session_id: uuid.UUID, db: DbSession, user: CurrentUser, title: str):
    """Delete every chunk whose metadata.title matches (query param `title`)."""
    require_owned_session(db, session_id, user)
    if not title.strip():
        return None
    delete_paper(str(session_id), title.strip())
    return None
