import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from backend.api import repos
from backend.api.auth import verify_access_token
from backend.api.db import get_db
from backend.api.models import SessionRow

DbSession = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    """Verify the Neon Auth (Better Auth) JWT from Authorization: Bearer <token>."""
    payload = verify_access_token(credentials.credentials)
    user_id = payload.get("sub")
    if not user_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Token is missing subject")
    return {
        "id": user_id,
        "email": payload.get("email"),
        "payload": payload,
    }


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_owned_session(
    db: Session, session_id: uuid.UUID | str, user: dict
) -> SessionRow:
    row = repos.get_session(db, session_id, user["id"])
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return row
