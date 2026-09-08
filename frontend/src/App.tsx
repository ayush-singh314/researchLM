import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, streamChat } from "./api";
import { ChatPane, ThinkingDots } from "./ChatPane";
import { NotesPane, type SaveStatus } from "./NotesPane";
import { ProfilePage } from "./ProfilePage";
import type { ChatMessage, Note, NoteSummary, Session } from "./types";

const CHAT_FALLBACK =
  "I couldn't find a reliable answer for that. It may not be covered in your sources, or something went wrong while I was working. Try asking again, or add the paper if it isn't indexed yet.";

const SESSION_KEY = "researchlm.activeSession";
const NOTES_WIDTH_KEY = "researchlm.notesWidth";
const SIDEBAR_KEY = "researchlm.sidebarCollapsed";
const DEFAULT_NOTES_WIDTH = 340;

function loadNotesWidth(): number {
  const raw = Number(localStorage.getItem(NOTES_WIDTH_KEY));
  if (!Number.isFinite(raw)) return DEFAULT_NOTES_WIDTH;
  return Math.min(720, Math.max(280, raw));
}

type AppProps = {
  userEmail?: string;
  onSignOut?: () => void;
};

type AppView = "chat" | "profile";

export function App({ userEmail, onSignOut }: AppProps) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<AppView>("chat");
  const [sessionId, setSessionId] = useState<string | null>(() => localStorage.getItem(SESSION_KEY));
  const [notesOpen, setNotesOpen] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem(SIDEBAR_KEY) === "1",
  );
  const [notesPending, setNotesPending] = useState<"create" | "generate" | null>(null);
  const [previewNonce, setPreviewNonce] = useState(0);
  const [ingestPending, setIngestPending] = useState<{ kind: "url" | "upload"; label: string } | null>(null);
  const [localMessages, setLocalMessages] = useState<ChatMessage[] | null>(null);
  const [draft, setDraft] = useState("");
  const [streaming, setStreaming] = useState("");
  const [busy, setBusy] = useState(false);
  const [agentThinking, setAgentThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [urlInput, setUrlInput] = useState("");
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null);
  const [noteTitle, setNoteTitle] = useState("");
  const [noteBody, setNoteBody] = useState("");
  const [noteDirty, setNoteDirty] = useState(false);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("idle");
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamBuf = useRef("");
  const flushTimer = useRef<number | null>(null);
  const appRef = useRef<HTMLDivElement>(null);
  const notesWidthRef = useRef(loadNotesWidth());
  const persistChain = useRef(Promise.resolve());
  const dirtyRef = useRef(false);
  const noteRef = useRef({
    sessionId: null as string | null,
    activeNoteId: null as string | null,
    title: "",
    body: "",
  });

  const sessionsQuery = useQuery({ queryKey: ["sessions"], queryFn: api.listSessions });
  const sessions = sessionsQuery.data || [];
  const sessionOwned = Boolean(sessionId && sessions.some((s) => s.id === sessionId));
  const activeSession = useMemo(
    () => sessions.find((s) => s.id === sessionId) || null,
    [sessions, sessionId],
  );

  useEffect(() => {
    if (sessionId) localStorage.setItem(SESSION_KEY, sessionId);
    else localStorage.removeItem(SESSION_KEY);
  }, [sessionId]);

  useEffect(() => {
    localStorage.setItem(SIDEBAR_KEY, sidebarCollapsed ? "1" : "0");
  }, [sidebarCollapsed]);

  useEffect(() => {
    if (!sessionsQuery.isSuccess) return;
    if (!sessions.length) {
      if (sessionId) setSessionId(null);
      return;
    }
    if (!sessionId || !sessions.some((s) => s.id === sessionId)) {
      setSessionId(sessions[0].id);
    }
  }, [sessionsQuery.isSuccess, sessions, sessionId]);

  const docsQuery = useQuery({
    queryKey: ["documents", sessionId],
    queryFn: () => api.listDocuments(sessionId!),
    enabled: Boolean(sessionId) && sessionOwned,
  });
  const notesQuery = useQuery({
    queryKey: ["notes", sessionId],
    queryFn: () => api.listNotes(sessionId!),
    enabled: Boolean(sessionId) && sessionOwned,
  });
  const messagesQuery = useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () => api.listMessages(sessionId!),
    enabled: Boolean(sessionId) && sessionsQuery.isSuccess && sessionOwned,
  });
  const allNotesQuery = useQuery({
    queryKey: ["notes", "all"],
    queryFn: () => api.listAllNotes(),
    enabled: view === "profile",
  });

  const messages = localMessages ?? messagesQuery.data ?? [];

  useEffect(() => {
    setLocalMessages(null);
  }, [sessionId]);

  noteRef.current = {
    sessionId,
    activeNoteId,
    title: noteTitle,
    body: noteBody,
  };

  useEffect(() => {
    appRef.current?.style.setProperty("--notes-width", `${notesWidthRef.current}px`);
  }, []);

  const applyNotesWidth = useCallback((px: number) => {
    const next = Math.min(720, Math.max(280, px));
    notesWidthRef.current = next;
    localStorage.setItem(NOTES_WIDTH_KEY, String(next));
    appRef.current?.style.setProperty("--notes-width", `${next}px`);
  }, []);

  const persistNote = useCallback(async (): Promise<boolean> => {
    const run = async (): Promise<boolean> => {
      const snap = noteRef.current;
      if (!snap.sessionId || !snap.activeNoteId || !dirtyRef.current) return true;
      setSaveStatus("saving");
      try {
        await api.updateNote(snap.sessionId, snap.activeNoteId, {
          title: snap.title,
          markdown: snap.body,
        });
        const latest = noteRef.current;
        const sameNote = latest.activeNoteId === snap.activeNoteId;
        const sameText = latest.title === snap.title && latest.body === snap.body;
        if (sameNote && sameText) {
          dirtyRef.current = false;
          setNoteDirty(false);
          setSaveStatus("saved");
        }
        queryClient.setQueryData(["notes", snap.sessionId], (old: Note[] | undefined) =>
          (old || []).map((n) =>
            n.id === snap.activeNoteId
              ? { ...n, title: snap.title, markdown: snap.body, updated_at: new Date().toISOString() }
              : n,
          ),
        );
        queryClient.invalidateQueries({ queryKey: ["notes", snap.sessionId] });
        queryClient.invalidateQueries({ queryKey: ["notes", "all"] });
        return true;
      } catch (err) {
        setSaveStatus("error");
        setError(err instanceof Error ? err.message : "Save failed");
        return false;
      }
    };

    const queued = persistChain.current.then(run, run);
    persistChain.current = queued.then(() => undefined, () => undefined);
    const ok = await queued;
    if (ok && dirtyRef.current) return persistNote();
    return ok;
  }, [queryClient]);

  useEffect(() => {
    if (!noteDirty) return;
    setSaveStatus("dirty");
    const timer = window.setTimeout(() => {
      void persistNote();
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [noteDirty, noteTitle, noteBody, persistNote]);

  useEffect(() => {
    if (!notesQuery.isSuccess) return;
    const notes = notesQuery.data;
    if (!notes.length) {
      if (!noteDirty) {
        setActiveNoteId(null);
        setNoteTitle("");
        setNoteBody("");
        setSaveStatus("idle");
      }
      return;
    }
    const current = notes.find((n) => n.id === activeNoteId);
    if (!current && !noteDirty) {
      const fallback = notes[0];
      setActiveNoteId(fallback.id);
      setNoteTitle(fallback.title);
      setNoteBody(fallback.markdown);
      setSaveStatus("idle");
      return;
    }
    if (current && !noteDirty) {
      setActiveNoteId(current.id);
      setNoteTitle(current.title);
      setNoteBody(current.markdown);
    }
  }, [notesQuery.isSuccess, notesQuery.data, activeNoteId, noteDirty]);

  const flushStream = useCallback(() => {
    setStreaming(streamBuf.current);
    bottomRef.current?.scrollIntoView({ behavior: "auto" });
  }, []);

  const onToken = useCallback(
    (token: string) => {
      streamBuf.current += token;
      if (flushTimer.current == null) {
        flushTimer.current = window.setTimeout(() => {
          flushTimer.current = null;
          flushStream();
        }, 50);
      }
    },
    [flushStream],
  );

  const selectThread = useCallback(
    async (id: string) => {
      const ok = await persistNote();
      if (!ok) return;
      setSessionId(id);
      dirtyRef.current = false;
      setNoteDirty(false);
      setSaveStatus("idle");
      setSidebarOpen(false);
      setView("chat");
      setError(null);
      void queryClient.refetchQueries({ queryKey: ["messages", id] });
      void queryClient.refetchQueries({ queryKey: ["notes", id] });
    },
    [queryClient, persistNote],
  );

  const createSession = useMutation({
    mutationFn: api.createSession,
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
      setSessionId(session.id);
      setLocalMessages([]);
      setView("chat");
      setSidebarOpen(false);
      dirtyRef.current = false;
      setNoteDirty(false);
      setActiveNoteId(null);
      setNoteTitle("");
      setNoteBody("");
      setSaveStatus("idle");
    },
  });

  async function selectNote(note: Note) {
    if (note.id === activeNoteId) return;
    const ok = await persistNote();
    if (!ok) return;
    setActiveNoteId(note.id);
    setNoteTitle(note.title);
    setNoteBody(note.markdown);
    dirtyRef.current = false;
    setNoteDirty(false);
    setSaveStatus("idle");
  }

  async function openNoteFromProfile(note: NoteSummary) {
    const ok = await persistNote();
    if (!ok) return;
    setView("chat");
    setNotesOpen(true);
    dirtyRef.current = false;
    setNoteDirty(false);
    setSaveStatus("idle");
    setActiveNoteId(note.id);
    setNoteTitle(note.title);
    setNoteBody(note.markdown);
    setSessionId(note.session_id);
    setSidebarOpen(false);
  }

  async function goProfile() {
    const ok = await persistNote();
    if (!ok) return;
    setView("profile");
    setSidebarOpen(false);
  }

  async function hideNotes() {
    const ok = await persistNote();
    if (!ok) return;
    setNotesOpen(false);
  }

  async function toggleNotes() {
    if (notesOpen) await hideNotes();
    else setNotesOpen(true);
  }

  async function sendMessage() {
    if (!sessionId || !draft.trim() || busy) return;
    const text = draft.trim();
    setDraft("");
    setError(null);
    setBusy(true);
    setAgentThinking(true);
    setLocalMessages((prev) => [...(prev ?? messagesQuery.data ?? []), { role: "user", content: text }]);
    streamBuf.current = "";
    setStreaming("");
    queueMicrotask(() => bottomRef.current?.scrollIntoView({ behavior: "auto" }));
    try {
      const result = await streamChat(sessionId, text, onToken);
      const answer = (result.answer || "").trim() || CHAT_FALLBACK;
      queryClient.setQueryData(["messages", sessionId], (old: ChatMessage[] | undefined) => [
        ...(old || []),
        { role: "user", content: text },
        { role: "assistant", content: answer },
      ]);
      setLocalMessages(null);
      if (result.session) {
        queryClient.setQueryData(["sessions"], (old: Session[] | undefined) =>
          (old || []).map((s) => (s.id === result.session!.id ? result.session! : s)),
        );
      }
      queryClient.invalidateQueries({ queryKey: ["sessions"] });
    } catch {
      const partial = streamBuf.current.trim();
      const answer = partial
        ? `${partial}\n\nI couldn't finish that answer. Please try asking again.`
        : CHAT_FALLBACK;
      queryClient.setQueryData(["messages", sessionId], (old: ChatMessage[] | undefined) => [
        ...(old || []),
        { role: "user", content: text },
        { role: "assistant", content: answer },
      ]);
      setLocalMessages(null);
    } finally {
      if (flushTimer.current != null) {
        window.clearTimeout(flushTimer.current);
        flushTimer.current = null;
      }
      streamBuf.current = "";
      setStreaming("");
      setAgentThinking(false);
      setBusy(false);
      bottomRef.current?.scrollIntoView({ behavior: "auto" });
    }
  }

  async function onUpload(files: FileList | null) {
    if (!sessionId || !files?.length) return;
    const names = Array.from(files).map((f) => f.name).join(", ");
    setBusy(true);
    setError(null);
    setIngestPending({ kind: "upload", label: names });
    try {
      const result = await api.uploadDocuments(sessionId, files);
      if (result.errors.length) setError(result.errors.join("; "));
      queryClient.invalidateQueries({ queryKey: ["documents", sessionId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setIngestPending(null);
      setBusy(false);
    }
  }

  async function onDeleteDocument(title: string) {
    if (!sessionId) return;
    if (!window.confirm(`Remove “${title}” from this chat?`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.deleteDocument(sessionId, title);
      queryClient.invalidateQueries({ queryKey: ["documents", sessionId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove document");
    } finally {
      setBusy(false);
    }
  }

  async function onUrls() {
    if (!sessionId) return;
    const urls = urlInput.split(/\s+/).map((u) => u.trim()).filter(Boolean);
    if (!urls.length) return;
    let label = urls[0];
    try {
      label = new URL(urls[0]).hostname || urls[0];
    } catch {
      /* keep raw */
    }
    setBusy(true);
    setError(null);
    setIngestPending({ kind: "url", label });
    try {
      const result = await api.loadUrls(sessionId, urls);
      setUrlInput("");
      if (result.errors.length) setError(result.errors.join("; "));
      queryClient.invalidateQueries({ queryKey: ["documents", sessionId] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "URL ingest failed");
    } finally {
      setIngestPending(null);
      setBusy(false);
    }
  }

  async function saveNote() {
    await persistNote();
  }

  function applyNote(note: Note) {
    setActiveNoteId(note.id);
    setNoteTitle(note.title);
    setNoteBody(note.markdown);
    dirtyRef.current = false;
    setNoteDirty(false);
    setSaveStatus("idle");
  }

  async function newNote() {
    if (!sessionId || notesPending) return;
    setNotesPending("create");
    try {
      const ok = await persistNote();
      if (!ok) return;
      const note = await api.createNote(sessionId);
      queryClient.invalidateQueries({ queryKey: ["notes", sessionId] });
      applyNote(note);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create note");
    } finally {
      setNotesPending(null);
    }
  }

  async function generateNote() {
    if (!sessionId) return;
    setBusy(true);
    setNotesPending("generate");
    setError(null);
    try {
      const ok = await persistNote();
      if (!ok) return;
      const note = await api.generateNote(sessionId);
      queryClient.invalidateQueries({ queryKey: ["notes", sessionId] });
      applyNote(note);
      setNotesOpen(true);
      setPreviewNonce((n) => n + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate notes");
    } finally {
      setNotesPending(null);
      setBusy(false);
    }
  }

  function toggleSidebar() {
    if (window.matchMedia("(max-width: 960px)").matches) {
      setSidebarOpen((open) => !open);
      return;
    }
    setSidebarCollapsed((v) => !v);
  }

  async function deleteNote(note: Note) {
    if (!sessionId) return;
    if (!window.confirm("Delete this note?")) return;
    if (note.id !== activeNoteId) {
      const ok = await persistNote();
      if (!ok) return;
    }
    try {
      await api.deleteNote(sessionId, note.id);
      const remaining = (notesQuery.data || []).filter((n) => n.id !== note.id);
      queryClient.setQueryData(["notes", sessionId], remaining);
      queryClient.invalidateQueries({ queryKey: ["notes", sessionId] });
      queryClient.invalidateQueries({ queryKey: ["notes", "all"] });
      if (note.id === activeNoteId) {
        const next = remaining[0];
        if (next) applyNote(next);
        else {
          setActiveNoteId(null);
          setNoteTitle("");
          setNoteBody("");
          dirtyRef.current = false;
          setNoteDirty(false);
          setSaveStatus("idle");
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  const showNotes = view === "chat" && notesOpen;
  const shellClass = [
    "app",
    showNotes ? "notes-open" : "",
    sidebarOpen ? "sidebar-open" : "",
    sidebarCollapsed ? "sidebar-collapsed" : "",
    view === "profile" ? "profile-open" : "",
  ].join(" ");

  return (
    <div
      ref={appRef}
      className={shellClass}
      style={{ ["--notes-width" as string]: `${notesWidthRef.current}px` }}
    >
      {(sidebarOpen || showNotes) && (
        <div className="overlay" onClick={() => { setSidebarOpen(false); }} />
      )}
      <Sidebar
        sessions={sessions}
        sessionId={sessionId}
        view={view}
        busy={busy}
        urlInput={urlInput}
        docTitles={docsQuery.data?.titles || []}
        ingestPending={ingestPending}
        onUrlInput={setUrlInput}
        onUrls={onUrls}
        onUpload={onUpload}
        onNewChat={() => {
          void persistNote().then((ok) => {
            if (ok) createSession.mutate();
          });
        }}
        onSelectThread={selectThread}
        onProfile={() => { void goProfile(); }}
        onDeleteDocument={(title) => { void onDeleteDocument(title); }}
      />

      {view === "profile" ? (
        <ProfilePage
          email={userEmail}
          notes={allNotesQuery.data || []}
          loading={allNotesQuery.isLoading}
          onOpenNote={openNoteFromProfile}
          onSignOut={onSignOut}
          onToggleSidebar={toggleSidebar}
          sidebarCollapsed={sidebarCollapsed}
        />
      ) : (
        <main className="chat">
          <div className="chat-header">
            <button className="btn menu-btn" onClick={toggleSidebar}>
              {sidebarCollapsed ? "Threads" : "Hide threads"}
            </button>
            <h2>{activeSession?.name || "Select a thread"}</h2>
            <button className="btn" onClick={() => { void toggleNotes(); }}>
              {notesOpen ? "Hide notes" : "Show notes"}
            </button>
          </div>

          {error && <div className="error">{error}</div>}

          <ChatPane
            messages={messages}
            streaming={streaming}
            thinking={agentThinking}
            messagesLoading={messagesQuery.isFetching && !messages.length}
            bottomRef={bottomRef}
          />

          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              sendMessage();
            }}
          >
            {busy && (
              <div className="composer-status" aria-live="polite">
                <span className="composer-status-dot" />
                {ingestPending
                  ? `Indexing ${ingestPending.label}`
                  : notesPending === "generate"
                    ? "Generating note"
                    : notesPending === "create"
                      ? "Creating note"
                      : streaming
                        ? "Writing answer"
                        : "Researcher is working"}
                <ThinkingDots />
              </div>
            )}
            <div className="composer-row">
              <textarea
                value={draft}
                placeholder={sessionId ? "Ask about your papers…" : "Create a chat first"}
                disabled={!sessionId || busy}
                rows={2}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
              />
              <button className="btn primary" type="submit" disabled={!sessionId || busy || !draft.trim()}>
                {agentThinking && !streaming ? "Working" : "Send"}
              </button>
            </div>
          </form>
        </main>
      )}

      {showNotes && (
        <NotesPane
          notes={notesQuery.data || []}
          notesReady={notesQuery.isSuccess}
          activeNoteId={activeNoteId}
          noteTitle={noteTitle}
          noteBody={noteBody}
          saveStatus={saveStatus}
          sessionId={sessionId}
          busy={busy}
          notesPending={notesPending}
          previewNonce={previewNonce}
          onSelectNote={(note) => { void selectNote(note); }}
          onTitle={(value) => {
            setNoteTitle(value);
            dirtyRef.current = true;
            setNoteDirty(true);
          }}
          onBody={(value) => {
            setNoteBody(value);
            dirtyRef.current = true;
            setNoteDirty(true);
          }}
          onNew={() => { void newNote(); }}
          onGenerate={() => { void generateNote(); }}
          onSave={() => { void saveNote(); }}
          onDelete={(note) => { void deleteNote(note); }}
          onClose={() => { void hideNotes(); }}
          onSetWidth={applyNotesWidth}
        />
      )}
    </div>
  );
}

const Sidebar = memo(function Sidebar({
  sessions,
  sessionId,
  view,
  busy,
  urlInput,
  docTitles,
  ingestPending,
  onUrlInput,
  onUrls,
  onUpload,
  onNewChat,
  onSelectThread,
  onProfile,
  onDeleteDocument,
}: {
  sessions: Session[];
  sessionId: string | null;
  view: AppView;
  busy: boolean;
  urlInput: string;
  docTitles: string[];
  ingestPending: { kind: "url" | "upload"; label: string } | null;
  onUrlInput: (value: string) => void;
  onUrls: () => void;
  onUpload: (files: FileList | null) => void;
  onNewChat: () => void;
  onSelectThread: (id: string) => void;
  onProfile: () => void;
  onDeleteDocument: (title: string) => void;
}) {
  const ingestDisabled = !sessionId || busy || Boolean(ingestPending);
  return (
    <aside className="sidebar">
      <div className="brand">
        <h1>ResearchLM</h1>
        <p>Papers, chat, notes</p>
      </div>
      <div className="sidebar-actions">
        <button className="btn primary compact" onClick={onNewChat} disabled={busy}>
          New chat
        </button>
        <button className={`btn compact ${view === "profile" ? "active" : ""}`} onClick={onProfile}>
          Profile
        </button>
      </div>
      <div className="threads">
        {sessions.map((session) => (
          <button
            key={session.id}
            className={`thread ${session.id === sessionId && view === "chat" ? "active" : ""}`}
            onClick={() => onSelectThread(session.id)}
          >
            {session.name}
            <small>{new Date(session.created_at).toLocaleString()}</small>
          </button>
        ))}
      </div>
      <div className="ingest">
        <strong className="ingest-title">Sources</strong>
        <label>
          Website URL
          <input
            value={urlInput}
            onChange={(e) => onUrlInput(e.target.value)}
            placeholder="https://example.com/paper"
            disabled={ingestDisabled}
            onKeyDown={(e) => {
              if (e.key === "Enter") onUrls();
            }}
          />
        </label>
        <label>
          Document upload
          <input
            type="file"
            multiple
            accept=".pdf,.txt,.md,.markdown"
            disabled={ingestDisabled}
            onChange={(e) => {
              onUpload(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
        {ingestPending && (
          <div className="doc-item pending">
            <span>Indexing {ingestPending.label}…</span>
          </div>
        )}
        {docTitles.length ? (
          <ul className="doc-list">
            {docTitles.map((title) => (
              <li key={title} className="doc-item">
                <span title={title}>{title}</span>
                <button
                  type="button"
                  className="doc-remove"
                  aria-label={`Remove ${title}`}
                  disabled={busy || !sessionId}
                  onClick={() => onDeleteDocument(title)}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        ) : !ingestPending ? (
          <p className="docs">
            {sessionId ? "Upload a paper or paste a URL" : "Create or select a chat first"}
          </p>
        ) : null}
      </div>
    </aside>
  );
});
