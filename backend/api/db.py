import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.api.models import Base


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://") and "+psycopg" not in url:
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return _normalize_database_url(url)


def get_psycopg_conninfo() -> str:
    """Plain postgresql:// DSN for psycopg / LangGraph (no SQLAlchemy driver).

    Prefer CHECKPOINT_DATABASE_URL for LangGraph's PostgresSaver. Fall back to
    DATABASE_URL_UNPOOLED (direct Neon host) and then DATABASE_URL.
    """
    raw = (
        os.environ.get("CHECKPOINT_DATABASE_URL", "").strip()
        or os.environ.get("DATABASE_URL_UNPOOLED", "").strip()
        or os.environ.get("DATABASE_URL", "").strip()
    )
    if not raw:
        raise RuntimeError("DATABASE_URL is not set")
    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]
    return raw.replace("postgresql+psycopg://", "postgresql://", 1)


engine = None
SessionLocal = None


def _ensure_user_id_columns(bind) -> None:
    """Add tenancy columns on existing tables (create_all will not ALTER)."""
    from sqlalchemy import inspect, text

    insp = inspect(bind)
    tables = set(insp.get_table_names())
    with bind.begin() as conn:
        if "sessions" in tables:
            session_cols = {c["name"] for c in insp.get_columns("sessions")}
            if "user_id" not in session_cols:
                conn.execute(text("DELETE FROM notes"))
                conn.execute(text("DELETE FROM sessions"))
                conn.execute(text("ALTER TABLE sessions ADD COLUMN user_id VARCHAR(255) NOT NULL"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions (user_id)"))
        if "notes" in tables:
            note_cols = {c["name"] for c in insp.get_columns("notes")}
            if "user_id" not in note_cols:
                conn.execute(text("DELETE FROM notes"))
                conn.execute(text("ALTER TABLE notes ADD COLUMN user_id VARCHAR(255) NOT NULL"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_notes_user_id ON notes (user_id)"))


def init_engine():
    global engine, SessionLocal
    engine = create_engine(get_database_url(), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    _ensure_user_id_columns(engine)
    return engine


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError("Database is not initialized")
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
