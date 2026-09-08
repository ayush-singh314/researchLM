import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.api import repos
from backend.api.deps import CurrentUser, DbSession, get_current_user, require_owned_session
from backend.api.schemas import NoteCreate, NoteOut, NoteSummaryOut, NoteUpdate
from backend.api.serialize import discussion_transcript, retrieved_summaries

router = APIRouter(prefix="/sessions", tags=["notes"], dependencies=[Depends(get_current_user)])
user_notes_router = APIRouter(tags=["notes"], dependencies=[Depends(get_current_user)])


@user_notes_router.get("/notes", response_model=list[NoteSummaryOut])
def list_my_notes(db: DbSession, user: CurrentUser, limit: int = 50):
    rows = repos.list_user_notes(db, user["id"], limit=min(max(limit, 1), 200))
    out: list[NoteSummaryOut] = []
    for note, session_name in rows:
        out.append(
            NoteSummaryOut(
                id=note.id,
                session_id=note.session_id,
                title=note.title,
                markdown=note.markdown,
                structured_json=note.structured_json,
                created_at=note.created_at,
                updated_at=note.updated_at,
                session_name=session_name,
            )
        )
    return out


@router.get("/{session_id}/notes", response_model=list[NoteOut])
def list_notes(session_id: uuid.UUID, db: DbSession, user: CurrentUser):
    require_owned_session(db, session_id, user)
    return repos.list_notes(db, session_id, user["id"])


@router.post("/{session_id}/notes", response_model=NoteOut)
def create_note(session_id: uuid.UUID, db: DbSession, user: CurrentUser, body: NoteCreate | None = None):
    require_owned_session(db, session_id, user)
    title = (body.title if body else None) or "Untitled"
    markdown = (body.markdown if body else None) or ""
    return repos.create_note(db, session_id, user["id"], title=title, markdown=markdown)


@router.patch("/{session_id}/notes/{note_id}", response_model=NoteOut)
def patch_note(
    session_id: uuid.UUID, note_id: uuid.UUID, body: NoteUpdate, db: DbSession, user: CurrentUser
):
    require_owned_session(db, session_id, user)
    row = repos.get_note(db, note_id, user["id"])
    if row is None or row.session_id != str(session_id):
        raise HTTPException(status_code=404, detail="Note not found")
    return repos.update_note(db, row, title=body.title, markdown=body.markdown)


@router.delete("/{session_id}/notes/{note_id}", status_code=204)
def remove_note(session_id: uuid.UUID, note_id: uuid.UUID, db: DbSession, user: CurrentUser):
    require_owned_session(db, session_id, user)
    row = repos.get_note(db, note_id, user["id"])
    if row is None or row.session_id != str(session_id):
        raise HTTPException(status_code=404, detail="Note not found")
    repos.delete_note(db, row)
    return None


@router.post("/{session_id}/notes/generate", response_model=NoteOut)
def generate_note(session_id: uuid.UUID, request: Request, db: DbSession, user: CurrentUser):
    require_owned_session(db, session_id, user)
    research_graph = request.app.state.research_graph
    notes_graph = request.app.state.notes_graph
    config = {"configurable": {"thread_id": str(session_id)}}
    try:
        state = research_graph.get_state(config)
        values = state.values if state else {}
    except Exception:
        values = {}

    result = notes_graph.invoke(
        {
            "session_id": str(session_id),
            "last_turns": discussion_transcript(values or {}),
            "retrieved_summaries": retrieved_summaries(values or {}, limit=8),
        }
    )
    if result.get("action") == "skip" or not result.get("markdown"):
        raise HTTPException(
            status_code=400,
            detail=result.get("skip_reason") or "Nothing to capture from the discussion yet.",
        )

    return repos.create_note(
        db,
        session_id,
        user["id"],
        title=result.get("title") or "Discussion notes",
        markdown=result["markdown"],
        structured_json=result.get("structured_json"),
    )
