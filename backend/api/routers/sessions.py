import uuid

from fastapi import APIRouter, Depends

from backend.api import repos
from backend.api.deps import CurrentUser, DbSession, get_current_user, require_owned_session
from backend.api.schemas import SessionCreate, SessionOut, SessionUpdate

router = APIRouter(prefix="/sessions", tags=["sessions"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=SessionOut)
def create_session(db: DbSession, user: CurrentUser, body: SessionCreate | None = None):
    name = body.name if body else None
    return repos.create_session(db, user["id"], name=name)


@router.get("", response_model=list[SessionOut])
def list_sessions(db: DbSession, user: CurrentUser):
    return repos.list_sessions(db, user["id"])


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: uuid.UUID, db: DbSession, user: CurrentUser):
    row = require_owned_session(db, session_id, user)
    return row


@router.patch("/{session_id}", response_model=SessionOut)
def patch_session(session_id: uuid.UUID, body: SessionUpdate, db: DbSession, user: CurrentUser):
    row = require_owned_session(db, session_id, user)
    return repos.rename_session(db, row, body.name, is_named=True)
