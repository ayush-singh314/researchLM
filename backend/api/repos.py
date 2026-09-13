"""SQLAlchemy data access for research sessions and study notes.

Routers call these helpers instead of querying `SessionRow` / `NoteRow` directly.
Tenancy is enforced here by filtering on `user_id` (JWT `sub`). Chat messages
are not stored in these tables; they live in the LangGraph Postgres checkpointer.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.models import NoteRow, SessionRow


def _sid(session_id: uuid.UUID | str) -> str:
    """Normalize a session/note id to the string PK used in Postgres."""
    return str(session_id)


def list_sessions(db: Session, user_id: str) -> list[SessionRow]:
    """Return this user's sessions, newest first (sidebar session list)."""
    stmt = (
        select(SessionRow)
        .where(SessionRow.user_id == user_id)
        .order_by(SessionRow.created_at.desc())
    ) #it is only a query object and it does not hit the postgres
    return list(db.scalars(stmt))


def get_session(db: Session, session_id: uuid.UUID | str, user_id: str) -> SessionRow | None:
    """Load one session if it exists and belongs to `user_id`; otherwise None."""
    row = db.get(SessionRow, _sid(session_id))
    if row is None or row.user_id != user_id:
        return None
    return row


def create_session(db: Session, user_id: str, name: str | None = None) -> SessionRow:
    """Insert a new workspace row. `is_named` is True only when a name is passed."""
    row = SessionRow(
        user_id=user_id,
        name=(name or "New Session").strip() or "New Session",
        is_named=bool(name),
    )
    db.add(row)
    db.flush()
    return row


def rename_session(db: Session, row: SessionRow, name: str, *, is_named: bool = True) -> SessionRow:
    """Update the session title (user rename or first-chat auto-title)."""
    row.name = name
    row.is_named = is_named
    db.flush() # send my pending db changes(jo change ham python object me kie pr postgres me nhi) to the sql
    # flush does not mean commit .... i.e  if something went wrong the middle , changes will be rolled back

    # use flush in the funntion when: "I've made the database change, but the caller still controls the overall transaction."
    return row


def list_user_notes(db: Session, user_id: str, limit: int = 50) -> list[tuple[NoteRow, str]]:
    """List this user's notes across sessions, with each parent session name."""
    stmt = (
        select(NoteRow, SessionRow.name)
        .join(SessionRow, SessionRow.id == NoteRow.session_id)
        .where(NoteRow.user_id == user_id)
        .order_by(NoteRow.updated_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).all())


def list_notes(db: Session, session_id: uuid.UUID | str, user_id: str) -> list[NoteRow]:
    """Return notes for one owned session, newest first."""
    stmt = (
        select(NoteRow)
        .where(NoteRow.session_id == _sid(session_id), NoteRow.user_id == user_id)
        .order_by(NoteRow.updated_at.desc())
    )
    return list(db.scalars(stmt))


def get_note(db: Session, note_id: uuid.UUID | str, user_id: str) -> NoteRow | None:
    """Load one note if it exists and belongs to `user_id`; otherwise None."""
    row = db.get(NoteRow, _sid(note_id))
    if row is None or row.user_id != user_id:
        return None
    return row


def create_note(
    db: Session,
    session_id: uuid.UUID | str,
    user_id: str,
    *,
    title: str = "Untitled",
    markdown: str = "",
    structured_json: dict | None = None,
) -> NoteRow:
    """Persist a generated (or empty) study note under a session, denormalizing `user_id`."""
    row = NoteRow(
        session_id=_sid(session_id),
        user_id=user_id,
        title=title or "Untitled",
        markdown=markdown or "",
        structured_json=structured_json,
    )
    db.add(row)
    db.flush()
    return row


def update_note(
    db: Session,
    row: NoteRow,
    *,
    title: str | None = None,
    markdown: str | None = None,
    structured_json: dict | None = None,
    set_structured: bool = False,
) -> NoteRow:
    """Patch title/markdown; `structured_json` is updated only when `set_structured` is True."""
    if title is not None:
        row.title = title
    if markdown is not None:
        row.markdown = markdown
    if set_structured:
        row.structured_json = structured_json
    db.flush()
    return row


def delete_note(db: Session, row: NoteRow) -> None:
    """Delete a note row. Caller must already have loaded an owned note."""
    db.delete(row)
    db.flush()
