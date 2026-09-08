import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.models import NoteRow, SessionRow


def _sid(session_id: uuid.UUID | str) -> str:
    return str(session_id)


def list_sessions(db: Session, user_id: str) -> list[SessionRow]:
    stmt = (
        select(SessionRow)
        .where(SessionRow.user_id == user_id)
        .order_by(SessionRow.created_at.desc())
    )
    return list(db.scalars(stmt))


def get_session(db: Session, session_id: uuid.UUID | str, user_id: str) -> SessionRow | None:
    row = db.get(SessionRow, _sid(session_id))
    if row is None or row.user_id != user_id:
        return None
    return row


def create_session(db: Session, user_id: str, name: str | None = None) -> SessionRow:
    row = SessionRow(
        user_id=user_id,
        name=(name or "New Session").strip() or "New Session",
        is_named=bool(name),
    )
    db.add(row)
    db.flush()
    return row


def rename_session(db: Session, row: SessionRow, name: str, *, is_named: bool = True) -> SessionRow:
    row.name = name
    row.is_named = is_named
    db.flush()
    return row


def list_user_notes(db: Session, user_id: str, limit: int = 50) -> list[tuple[NoteRow, str]]:
    stmt = (
        select(NoteRow, SessionRow.name)
        .join(SessionRow, SessionRow.id == NoteRow.session_id)
        .where(NoteRow.user_id == user_id)
        .order_by(NoteRow.updated_at.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).all())


def list_notes(db: Session, session_id: uuid.UUID | str, user_id: str) -> list[NoteRow]:
    stmt = (
        select(NoteRow)
        .where(NoteRow.session_id == _sid(session_id), NoteRow.user_id == user_id)
        .order_by(NoteRow.updated_at.desc())
    )
    return list(db.scalars(stmt))


def get_note(db: Session, note_id: uuid.UUID | str, user_id: str) -> NoteRow | None:
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
    if title is not None:
        row.title = title
    if markdown is not None:
        row.markdown = markdown
    if set_structured:
        row.structured_json = structured_json
    db.flush()
    return row


def delete_note(db: Session, row: NoteRow) -> None:
    db.delete(row)
    db.flush()
