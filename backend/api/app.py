import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("USER_AGENT", "ResearchLM/0.1")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.checkpoint import close_checkpoint_pool, init_checkpointer
from backend.api.db import init_engine
from backend.api.deps import CurrentUser
from backend.api.routers import chat, ingest, notes, sessions
from backend.notes.graph import build_notes_graph
from backend.rag.graph import build_graph


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_engine()
    pool, saver = init_checkpointer()
    app.state.checkpoint_pool = pool
    app.state.research_graph = build_graph(checkpointer=saver)
    app.state.notes_graph = build_notes_graph()
    try:
        yield
    finally:
        close_checkpoint_pool(pool)


def create_app() -> FastAPI:
    app = FastAPI(title="ResearchLM", lifespan=lifespan)
    origins = [
        origin.strip()
        for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(sessions.router)
    app.include_router(ingest.router)
    app.include_router(chat.router)
    app.include_router(notes.user_notes_router)
    app.include_router(notes.router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/me")
    def me(user: CurrentUser):
        return {"id": user["id"], "email": user.get("email")}

    return app
