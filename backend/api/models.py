"""SQLAlchemy models for public.sessions and public.notes.

mapped_column maps a typed attribute to a Postgres column.
relationship is ORM-only (not a column): it loads related rows.
Chat history is not here; it lives in LangGraph checkpoints keyed by session id.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Shared metadata base for all app tables."""

    pass


def _utcnow() -> datetime:
    """Python-side default when the DB server_default is not used yet."""
    return datetime.now(timezone.utc)


def _uuid_str() -> str:
    """New session/note primary key as a UUID string."""
    return str(uuid.uuid4())


class SessionRow(Base):
    """Workspace / chat-thread header. Id is reused as LangGraph thread_id and Qdrant collection key."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)  # workspace UUID
    user_id: Mapped[str] = mapped_column(String(255), index=True)  # Neon Auth JWT sub
    name: Mapped[str] = mapped_column(String(255), default="New Session")  # sidebar title
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_utcnow
    )
    is_named: Mapped[bool] = mapped_column(Boolean, default=False)  # True after the user sets a name
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # optional bag; not chat content

    notes: Mapped[list["NoteRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"  # cascade:deleting a session deletes its notes
                                                    #back_populates: keep the session.notes in sync
    )


class NoteRow(Base):
    """Editable study note. Own id; belongs to a session via session_id."""

    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid_str)  # note UUID
    user_id: Mapped[str] = mapped_column(String(255), index=True)  # owner; same as session.user_id
    session_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sessions.id", ondelete="CASCADE")  # parent workspace; cascade on session delete
    )
    title: Mapped[str] = mapped_column(String(255), default="Untitled")
    markdown: Mapped[str] = mapped_column(Text, default="")  # note body
    structured_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # optional structured note payload
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), default=_utcnow, onupdate=_utcnow
    )

    session: Mapped[SessionRow] = relationship(back_populates="notes")  # parent SessionRow
