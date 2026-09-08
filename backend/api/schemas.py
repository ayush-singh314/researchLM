import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    name: str | None = None


class SessionUpdate(BaseModel):
    name: str


class SessionOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    is_named: bool

    model_config = {"from_attributes": True}


class UrlsIn(BaseModel):
    urls: list[str] = Field(min_length=1)


class ChatIn(BaseModel):
    message: str = Field(min_length=1)


class BtwIn(BaseModel):
    query: str = Field(min_length=1)


class ChatMessageOut(BaseModel):
    role: str
    content: str
    turn: int | None = None


class NoteCreate(BaseModel):
    title: str | None = None
    markdown: str | None = None


class NoteUpdate(BaseModel):
    title: str | None = None
    markdown: str | None = None


class NoteOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    title: str
    markdown: str
    structured_json: dict | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteSummaryOut(NoteOut):
    session_name: str


class DocumentListOut(BaseModel):
    titles: list[str]


class IngestResult(BaseModel):
    added: list[str]
    errors: list[str] = Field(default_factory=list)
