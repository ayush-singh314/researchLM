"""HTTP request/response shapes for the FastAPI routers.

These Pydantic models are the API contract: they validate incoming JSON and
control what leaves the API. They are not database tables — those live in
`models.py`. Chat text is not a schema-backed table; `ChatMessageOut` is built
from LangGraph checkpoint state in `serialize.py`.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    """POST /sessions body. Optional name; omit or null → 'New Session'."""

    name: str | None = None


class SessionUpdate(BaseModel):
    """PATCH /sessions/{id} body. Required new title (`is_named=True` in repos)."""

    name: str


class SessionOut(BaseModel):
    """Session JSON for list/get/create/patch and the chat SSE `done` payload.

    Built from `SessionRow` via `from_attributes`. Does not include user_id or chat.
    """

    id: uuid.UUID
    name: str
    created_at: datetime
    is_named: bool

    model_config = {"from_attributes": True}


class UrlsIn(BaseModel):
    """POST /sessions/{id}/urls body. At least one URL to ingest into Qdrant."""

    urls: list[str] = Field(min_length=1)


class ChatIn(BaseModel):
    """POST /sessions/{id}/chat body. Non-empty user prompt for the researcher graph."""

    message: str = Field(min_length=1)


class BtwIn(BaseModel):
    """POST /sessions/{id}/btw body. Side-channel query; UI does not call this yet."""

    query: str = Field(min_length=1)


class ChatMessageOut(BaseModel):
    """One bubble from GET /sessions/{id}/messages (`messages_from_graph_state`).

    `turn` is set on assistant messages, None on user messages.
    """

    role: str
    content: str
    turn: int | None = None


class NoteCreate(BaseModel):
    """POST /sessions/{id}/notes body. Empty note; generate uses the graph instead."""

    title: str | None = None
    markdown: str | None = None


class NoteUpdate(BaseModel):
    """PATCH /sessions/{id}/notes/{note_id} body. Partial title/markdown edit."""

    title: str | None = None
    markdown: str | None = None


class NoteOut(BaseModel):
    """Full note JSON after create/get/patch/generate. Maps from `NoteRow`."""

    id: uuid.UUID
    session_id: uuid.UUID
    title: str
    markdown: str
    structured_json: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteSummaryOut(NoteOut):
    """GET /notes item: same as NoteOut plus parent session name for the notes list."""

    session_name: str


class DocumentListOut(BaseModel):
    """GET /sessions/{id}/documents. Paper titles in that session's Qdrant collection."""

    titles: list[str]


class IngestResult(BaseModel):
    """POST documents/urls response. `added` titles indexed; `errors` per failed file/URL."""

    added: list[str]
    errors: list[str] = Field(default_factory=list)