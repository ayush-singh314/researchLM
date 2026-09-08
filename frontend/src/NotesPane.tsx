import { memo, useEffect, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent } from "react";
import { createPortal } from "react-dom";
import { ChatMarkdown } from "./ChatMarkdown";
import type { Note } from "./types";

export type SaveStatus = "idle" | "dirty" | "saving" | "saved" | "error";

type Props = {
  notes: Note[];
  notesReady: boolean;
  activeNoteId: string | null;
  noteTitle: string;
  noteBody: string;
  saveStatus: SaveStatus;
  sessionId: string | null;
  busy: boolean;
  notesPending?: "create" | "generate" | null;
  previewNonce?: number;
  onSelectNote: (note: Note) => void;
  onTitle: (value: string) => void;
  onBody: (value: string) => void;
  onNew: () => void;
  onGenerate: () => void;
  onSave: () => void;
  onDelete: (note: Note) => void;
  onClose: () => void;
  onSetWidth: (px: number) => void;
};

const DEFAULT_WIDTH = 340;
const MIN_WIDTH = 280;
const MAX_WIDTH = 720;
const LIST_KEY = "researchlm.notesListOpen";

function snippet(markdown: string): string {
  const text = markdown.replace(/\s+/g, " ").trim();
  if (!text) return "Empty note";
  return text.length > 80 ? `${text.slice(0, 80)}…` : text;
}

function relativeTime(iso: string): string {
  const date = new Date(iso);
  const diff = Date.now() - date.getTime();
  const minutes = Math.max(0, Math.round(diff / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}

function isMobileNotes(): boolean {
  return window.matchMedia("(max-width: 960px)").matches;
}

function statusLabel(status: SaveStatus): string {
  if (status === "saving") return "Saving…";
  if (status === "saved") return "Saved";
  if (status === "dirty") return "Unsaved";
  if (status === "error") return "Save failed";
  return "";
}

function safeFilename(title: string): string {
  const base = title.trim() || "notes";
  return `${base.replace(/[\\/:*?"<>|]+/g, "-").replace(/\s+/g, " ").trim()}.md`;
}

function downloadMarkdown(title: string, body: string) {
  const blob = new Blob([body], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = safeFilename(title);
  link.click();
  URL.revokeObjectURL(url);
}

export const NotesPane = memo(function NotesPane({
  notes,
  notesReady,
  activeNoteId,
  noteTitle,
  noteBody,
  saveStatus,
  sessionId,
  busy,
  notesPending,
  previewNonce = 0,
  onSelectNote,
  onTitle,
  onBody,
  onNew,
  onGenerate,
  onSave,
  onDelete,
  onClose,
  onSetWidth,
}: Props) {
  const [fullscreen, setFullscreen] = useState(false);
  const [listOpen, setListOpen] = useState(() => localStorage.getItem(LIST_KEY) === "1");
  const dirty = saveStatus === "dirty" || saveStatus === "saving";
  const showList = listOpen;

  useEffect(() => {
    localStorage.setItem(LIST_KEY, listOpen ? "1" : "0");
  }, [listOpen]);

  useEffect(() => {
    if (previewNonce > 0) setFullscreen(true);
  }, [previewNonce]);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setFullscreen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [fullscreen]);

  function onHandlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    if (isMobileNotes()) return;
    event.preventDefault();
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    const onMove = (ev: PointerEvent) => {
      const next = Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, window.innerWidth - ev.clientX));
      onSetWidth(next);
    };
    const onUp = () => {
      handle.releasePointerCapture(event.pointerId);
      handle.removeEventListener("pointermove", onMove);
      handle.removeEventListener("pointerup", onUp);
    };
    handle.addEventListener("pointermove", onMove);
    handle.addEventListener("pointerup", onUp);
  }

  function closePreview() {
    setFullscreen(false);
  }

  const previewOverlay = fullscreen
    ? createPortal(
        <div className="note-fullscreen" role="dialog" aria-modal="true" aria-label="Note preview">
          <div className="note-fullscreen-bar">
            <strong>{noteTitle.trim() || "Untitled"}</strong>
            <div className="note-fullscreen-actions">
              <button type="button" className="btn" onClick={() => downloadMarkdown(noteTitle, noteBody)}>
                Download .md
              </button>
              <button type="button" className="btn primary" onClick={closePreview}>
                Close preview
              </button>
            </div>
          </div>
          <div className="note-fullscreen-body">
            {noteBody.trim() ? (
              <ChatMarkdown content={noteBody} />
            ) : (
              <div className="empty">Nothing to preview yet.</div>
            )}
          </div>
        </div>,
        document.body,
      )
    : null;

  return (
    <aside
      className="notes"
      tabIndex={-1}
      onKeyDown={(event: KeyboardEvent<HTMLElement>) => {
        if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
          event.preventDefault();
          onSave();
        }
        if (event.key === "Escape") {
          event.preventDefault();
          if (fullscreen) closePreview();
          else onClose();
        }
      }}
    >
      {previewOverlay}
      <div
        className="notes-resize"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize notes"
        onPointerDown={onHandlePointerDown}
        onDoubleClick={() => {
          if (!isMobileNotes()) onSetWidth(DEFAULT_WIDTH);
        }}
      />
      <div className="notes-header">
        <div className="notes-header-row">
          <strong>Notes</strong>
          <span className={`notes-status status-${saveStatus}`}>
            {notesPending === "create"
              ? "Creating…"
              : notesPending === "generate"
                ? "Crafting notes…"
                : statusLabel(saveStatus)}
          </span>
        </div>
        <button
          type="button"
          className="btn notes-list-toggle"
          aria-expanded={showList}
          onClick={() => setListOpen((open) => !open)}
        >
          {showList ? "Hide all notes" : `All notes (${notes.length})`}
        </button>
        <div className="note-actions">
          <button className="btn" onClick={onNew} disabled={!sessionId || busy || Boolean(notesPending)}>
            + New note
          </button>
          <button
            className="btn craft"
            onClick={onGenerate}
            disabled={!sessionId || busy || Boolean(notesPending)}
            title="Generate context-aware, personalized notes from this discussion."
          >
            Craft notes from chat
          </button>
        </div>
      </div>
      {showList && (
      <div className="notes-list">
        {notesPending === "create" && (
          <div className="note-item pending">
            <div className="note-item-main">
              <span className="note-item-title">Untitled</span>
              <span className="note-item-snippet">Creating note…</span>
            </div>
          </div>
        )}
        {notesPending === "generate" && (
          <div className="note-item pending">
            <div className="note-item-main">
              <span className="note-item-title">Study notes</span>
              <span className="note-item-snippet">Planning sections and writing from the chat…</span>
            </div>
          </div>
        )}
        {notes.map((note) => {
          const live = note.id === activeNoteId;
          const title = (live ? noteTitle : note.title).trim() || "Untitled";
          const body = live ? noteBody : note.markdown;
          return (
            <div
              key={note.id}
              className={`note-item ${live ? "active" : ""}`}
              onClick={() => {
                onSelectNote(note);
                setListOpen(false);
              }}
            >
              <div className="note-item-main">
                <span className="note-item-title">
                  {live && dirty ? "• " : ""}
                  {title}
                </span>
                <span className="note-item-snippet">{snippet(body)}</span>
                <small>{relativeTime(note.updated_at)}</small>
              </div>
              <button
                className="note-delete"
                type="button"
                aria-label={`Delete ${title}`}
                onClick={(event) => {
                  event.stopPropagation();
                  onDelete(note);
                }}
              >
                ×
              </button>
            </div>
          );
        })}
      </div>
      )}
      {activeNoteId ? (
        <div className="note-editor">
          <input
            value={noteTitle}
            onChange={(e) => onTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.preventDefault();
            }}
            placeholder="Untitled"
          />
          <div className="note-mode">
            <button type="button" className="btn active">
              Edit
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => setFullscreen(true)}
              disabled={!noteBody.trim()}
            >
              Preview
            </button>
          </div>
          <textarea
            value={noteBody}
            onChange={(e) => onBody(e.target.value)}
            placeholder="Write or craft notes from the discussion"
          />
          <div className="note-editor-actions">
            <button
              className="btn"
              type="button"
              onClick={() => downloadMarkdown(noteTitle, noteBody)}
              disabled={!noteBody.trim()}
            >
              Download .md
            </button>
            <button className="btn primary" onClick={onSave} disabled={saveStatus === "saving" || !sessionId}>
              Save
            </button>
          </div>
        </div>
      ) : (
        <div className="empty">
          {!notesReady
            ? "Loading notes…"
            : "Open a note or create one. Craft notes from chat builds a study note from this thread."}
        </div>
      )}
    </aside>
  );
});
