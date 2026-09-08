"""Supervisor → planner → section writers for study notes from a chat.

Persistence happens in the API layer so users can still PATCH notes in Postgres.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

llm = ChatGroq(model="openai/gpt-oss-120b")

MAX_HEADINGS = 6
GROUNDING_CAP = 14000


class NotesState(TypedDict, total=False):
    session_id: str
    last_turns: str
    retrieved_summaries: str
    topic: str
    user_questions: list[str]
    headings: list[str]
    sections: list[dict]
    action: Literal["new", "skip"]
    title: str
    markdown: str
    structured_json: dict | None
    skip_reason: str | None


class SupervisorOut(BaseModel):
    action: Literal["new", "skip"]
    topic: str = ""
    user_questions: list[str] = Field(default_factory=list)
    reason: str = ""


class PlannerOut(BaseModel):
    title: str = Field(description="Short note title")
    headings: list[str] = Field(description="3 to 6 study-note subheadings")


class SectionOut(BaseModel):
    markdown: str = Field(description="One markdown section starting with ## heading")


def _grounding(state: NotesState) -> str:
    discussion = (state.get("last_turns") or "").strip()[:GROUNDING_CAP]
    evidence = (state.get("retrieved_summaries") or "").strip()[:4000]
    return (
        "Use ONLY the discussion and retrieved evidence below. "
        "Do not invent facts, citations, numbers, or examples that are not present.\n\n"
        f"Discussion:\n{discussion or '(empty)'}\n\n"
        f"Retrieved evidence:\n{evidence or '(none)'}\n"
    )


def supervisor_node(state: NotesState) -> dict:
    turns = (state.get("last_turns") or "").strip()
    if not turns:
        return {"action": "skip", "skip_reason": "No discussion yet."}

    out: SupervisorOut = llm.with_structured_output(SupervisorOut).invoke(
        [
            {
                "role": "user",
                "content": (
                    "You supervise study-note generation from a paper Q&A chat.\n"
                    "If the thread is empty, greeting-only, or has no research questions, action=skip.\n"
                    "Otherwise action=new. Extract a short topic and the user's questions "
                    "(paraphrase lightly, do not add new questions).\n\n"
                    f"{_grounding(state)}"
                ),
            }
        ]
    )
    if out.action == "skip":
        return {"action": "skip", "skip_reason": out.reason or "Nothing to capture from the discussion yet."}
    return {
        "action": "new",
        "topic": (out.topic or "Discussion").strip(),
        "user_questions": [q.strip() for q in out.user_questions if q.strip()][:8],
    }


def planner_node(state: NotesState) -> dict:
    questions = state.get("user_questions") or []
    qblock = "\n".join(f"- {q}" for q in questions) or "(none listed)"
    out: PlannerOut = llm.with_structured_output(PlannerOut).invoke(
        [
            {
                "role": "user",
                "content": (
                    "Plan study notes for this discussion. Return a short title and 3-6 "
                    "subheadings that cover the user's questions and the topic. "
                    "Headings only — no body text.\n\n"
                    f"Topic: {state.get('topic') or 'Discussion'}\n"
                    f"User questions:\n{qblock}\n\n"
                    f"{_grounding(state)}"
                ),
            }
        ]
    )
    headings = [h.strip() for h in out.headings if h.strip()][:MAX_HEADINGS]
    if len(headings) < 2:
        headings = headings or [state.get("topic") or "Key points"]
        if len(headings) == 1:
            headings.append("Takeaways")
    return {
        "title": (out.title or state.get("topic") or "Discussion notes").strip(),
        "headings": headings,
    }


def write_sections_node(state: NotesState) -> dict:
    headings = state.get("headings") or []
    writer = llm.with_structured_output(SectionOut)
    topic = state.get("topic") or "Discussion"
    sections: list[dict] = []
    for heading in headings:
        written: SectionOut = writer.invoke(
            [
                {
                    "role": "user",
                    "content": (
                        "Write one study-note section that helps the reader understand and "
                        "internalize this concept. Use markdown: start with `## {heading}`, "
                        "then short paragraphs and bullets. Optional mermaid fenced diagram "
                        "ONLY if the source already describes a process, architecture, or flow.\n"
                        "Do not invent claims, citations, numbers, or examples. "
                        "If the source does not cover this heading, write 1-2 sentences saying so.\n\n"
                        f"Note topic: {topic}\n"
                        f"This section heading: {heading}\n\n"
                        f"{_grounding(state)}"
                    ),
                }
            ]
        )
        body = (written.markdown or "").strip()
        if not body.startswith("#"):
            body = f"## {heading}\n\n{body}"
        sections.append({"heading": heading, "markdown": body})
    return {"sections": sections}


def assemble_node(state: NotesState) -> dict:
    title = (state.get("title") or state.get("topic") or "Discussion notes").strip()
    parts = [f"# {title}"]
    topic = (state.get("topic") or "").strip()
    questions = state.get("user_questions") or []
    if topic:
        parts.append(f"_{topic}_")
    if questions:
        qlines = "\n".join(f"- {q}" for q in questions)
        parts.append(f"## What you asked\n\n{qlines}")
    for section in state.get("sections") or []:
        md = (section.get("markdown") or "").strip()
        if md:
            parts.append(md)
    markdown = "\n\n".join(parts).strip()
    return {
        "action": "new",
        "title": title,
        "markdown": markdown,
        "structured_json": {
            "topic": topic,
            "headings": state.get("headings") or [],
            "user_questions": questions,
        },
    }


def after_supervisor(state: NotesState) -> str:
    if state.get("action") == "skip":
        return "end"
    return "planner"


def build_notes_graph():
    graph = StateGraph(NotesState)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("planner", planner_node)
    graph.add_node("write_sections", write_sections_node)
    graph.add_node("assemble", assemble_node)
    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        after_supervisor,
        {"planner": "planner", "end": END},
    )
    graph.add_edge("planner", "write_sections")
    graph.add_edge("write_sections", "assemble")
    graph.add_edge("assemble", END)
    return graph.compile()
