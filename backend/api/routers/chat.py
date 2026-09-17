import json
import logging
import uuid
from typing import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, HumanMessage
from langchain_groq import ChatGroq

from backend.api import repos
from backend.api.deps import CurrentUser, DbSession, get_current_user, require_owned_session
from backend.api.schemas import BtwIn, ChatIn, ChatMessageOut, SessionOut
from backend.api.serialize import messages_from_graph_state, serialize_state
from backend.rag.btw_handler import handle_btw

router = APIRouter(prefix="/sessions", tags=["chat"], dependencies=[Depends(get_current_user)])

CHAT_FALLBACK = (
    "I couldn't find a reliable answer for that. It may not be covered in your sources, "
    "or something went wrong while I was working. Try asking again, or add the paper "
    "if it isn't indexed yet."
)

_rename_llm = ChatGroq(model="openai/gpt-oss-120b")


def generate_session_name(first_message: str) -> str:
    try:
        response = _rename_llm.invoke(
            [
                {
                    "role": "system",
                    "content": (
                        "Generate a concise 3-5 word title for a research chat session "
                        "based on the user's first message. Return only the title, "
                        "no punctuation at the end, no quotes."
                    ),
                },
                {"role": "user", "content": first_message[:500]},
            ]
        )
        return response.content.strip()
    except Exception:
        return "New Session"


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _message_chunk_text(chunk) -> str:
    """Delta text from an LLM stream chunk (not a completed AIMessage)."""
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text") or "")
        return "".join(parts)
    return ""


def _initial_rag_state(session_id: str, prompt: str) -> dict:
    return {
        "messages": [HumanMessage(content=prompt)],
        "session_id": session_id,
        "query": prompt,
        "route": None,
        "retrieved_docs": [],
        "retrieval_attempts": 0,
        "claim_verdict": None,
        "claim_source": None,
        "superseding_papers": [],
        "answer": None,
        "is_relevant": None,
        "rewrite_count": 0,
    }


@router.get("/{session_id}/messages", response_model=list[ChatMessageOut])
def get_messages(session_id: uuid.UUID, request: Request, db: DbSession, user: CurrentUser):
    require_owned_session(db, session_id, user)
    graph = request.app.state.research_graph
    config = {"configurable": {"thread_id": str(session_id)}}
    try:
        state = graph.get_state(config)
        if not state or not state.values:
            return []
        return messages_from_graph_state(state.values)
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to load graph messages for session %s", session_id
        )
        raise HTTPException(status_code=500, detail="Could not load conversation")


@router.post("/{session_id}/chat")
def chat(session_id: uuid.UUID, body: ChatIn, request: Request, db: DbSession, user: CurrentUser):
    row = require_owned_session(db, session_id, user)
    graph = request.app.state.research_graph
    sid = str(session_id)
    prompt = body.message.strip()
    config = {"configurable": {"thread_id": sid}}

    renamed = None
    if not row.is_named:
        renamed = generate_session_name(prompt)
        repos.rename_session(db, row, renamed, is_named=True)
        db.commit()

    def events() -> Iterator[str]:
        response_text = ""
        try:
            for chunk, metadata in graph.stream(
                _initial_rag_state(sid, prompt),
                config,
                stream_mode="messages",
            ):
                # Token deltas only. The node also returns a full AIMessage; streaming
                # that would concatenate the answer twice in the UI.
                if metadata.get("langgraph_node") != "generate_answer":
                    continue
                if not isinstance(chunk, AIMessageChunk):
                    continue
                delta = _message_chunk_text(chunk)
                if not delta:
                    continue
                if response_text and delta == response_text:
                    continue
                response_text += delta
                yield _sse("token", {"text": delta})

            final_values = graph.get_state(config).values
            if not (response_text or "").strip():
                response_text = (final_values.get("answer") or "").strip() or CHAT_FALLBACK
                yield _sse("token", {"text": response_text})

            payload = {
                "answer": response_text,
                "graph_state": serialize_state(final_values),
                "session": SessionOut.model_validate(row).model_dump(mode="json"),
            }
            yield _sse("done", payload)
        except Exception:
            logging.getLogger(__name__).exception("Chat stream failed for session %s", sid)
            yield _sse("error", {"detail": CHAT_FALLBACK})

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/{session_id}/btw")
def btw(session_id: uuid.UUID, body: BtwIn, db: DbSession, user: CurrentUser):
    require_owned_session(db, session_id, user)

    def events() -> Iterator[str]:
        try:
            for chunk in handle_btw(body.query.strip()):
                if chunk:
                    yield _sse("token", {"text": chunk})
            yield _sse("done", {"answer": None})
        except Exception as exc:
            yield _sse("error", {"detail": str(exc)})

    return StreamingResponse(events(), media_type="text/event-stream")
