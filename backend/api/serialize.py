from langchain_core.documents import Document


def serialize_state(values: dict) -> dict:
    out = {}
    for key, value in values.items():
        if key == "messages":
            out[key] = [
                {
                    "type": type(msg).__name__,
                    "content": (
                        msg.content[:300]
                        if isinstance(msg.content, str)
                        else repr(msg.content)[:300]
                    ),
                }
                for msg in (value or [])
            ]
        elif key == "retrieved_docs":
            out[key] = [
                {"content": doc.page_content[:300], "metadata": doc.metadata}
                for doc in (value or [])
            ]
        else:
            out[key] = value
    return out


def messages_from_graph_state(values: dict) -> list[dict]:
    chats: list[dict] = []
    turn = 0
    for msg in values.get("messages") or []:
        type_name = type(msg).__name__
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        if type_name == "HumanMessage":
            chats.append({"role": "user", "content": content, "turn": None})
        elif type_name in ("AIMessage", "AIMessageChunk"):
            if getattr(msg, "tool_calls", None):
                continue
            if not content:
                continue
            turn += 1
            chats.append({"role": "assistant", "content": content, "turn": turn})
    return chats


def last_turns_text(values: dict, max_turns: int = 4) -> str:
    messages = messages_from_graph_state(values)
    recent = messages[-max_turns * 2 :]
    lines = []
    for msg in recent:
        role = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content']}")
    return "\n\n".join(lines)


def discussion_transcript(values: dict, max_chars: int = 12000) -> str:
    """Longer grounded transcript for note generation (all user turns + recent answers)."""
    messages = messages_from_graph_state(values)
    if not messages:
        return ""
    users = [m for m in messages if m["role"] == "user"]
    assistants = [m for m in messages if m["role"] == "assistant"]
    recent_assistants = assistants[-12:]
    parts: list[str] = []
    if users:
        parts.append("User questions:")
        for msg in users:
            parts.append(f"- {msg['content']}")
    if recent_assistants:
        parts.append("Assistant answers:")
        for msg in recent_assistants:
            parts.append(f"Assistant: {msg['content']}")
    text = "\n\n".join(parts)
    if len(text) > max_chars:
        return text[: max_chars - 20].rstrip() + "\n\n[truncated]"
    return text


def retrieved_summaries(values: dict, limit: int = 4) -> str:
    docs: list[Document] = values.get("retrieved_docs") or []
    parts = []
    for doc in docs[:limit]:
        title = (doc.metadata or {}).get("title", "")
        parts.append(f"{title}: {doc.page_content[:400]}")
    return "\n\n".join(parts)
