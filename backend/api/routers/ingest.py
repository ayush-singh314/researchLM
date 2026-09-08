import uuid

from fastapi import APIRouter, Depends, File, UploadFile

from backend.api.deps import CurrentUser, DbSession, get_current_user, require_owned_session
from backend.api.ingest import ingest_upload, ingest_urls
from backend.api.schemas import DocumentListOut, IngestResult, UrlsIn
from backend.rag.vector_store import delete_paper, list_papers

router = APIRouter(prefix="/sessions", tags=["ingest"], dependencies=[Depends(get_current_user)])

ALLOWED_SUFFIXES = {".pdf", ".txt", ".md", ".markdown"}


@router.post("/{session_id}/documents", response_model=IngestResult)
async def upload_documents(
    session_id: uuid.UUID,
    db: DbSession,
    user: CurrentUser,
    files: list[UploadFile] = File(...),
):
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
    return IngestResult(added=added, errors=errors)


@router.post("/{session_id}/urls", response_model=IngestResult)
def load_urls(session_id: uuid.UUID, body: UrlsIn, db: DbSession, user: CurrentUser):
    require_owned_session(db, session_id, user)
    added, errors = ingest_urls(str(session_id), body.urls)
    return IngestResult(added=added, errors=errors)


@router.get("/{session_id}/documents", response_model=DocumentListOut)
def get_documents(session_id: uuid.UUID, db: DbSession, user: CurrentUser):
    require_owned_session(db, session_id, user)
    try:
        titles = list_papers(str(session_id))
    except Exception:
        titles = []
    return DocumentListOut(titles=titles)


@router.delete("/{session_id}/documents", status_code=204)
def remove_document(session_id: uuid.UUID, db: DbSession, user: CurrentUser, title: str):
    require_owned_session(db, session_id, user)
    if not title.strip():
        return None
    delete_paper(str(session_id), title.strip())
    return None
