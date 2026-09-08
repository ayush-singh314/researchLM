import { useMemo } from "react";
import type { NoteSummary } from "./types";

type Props = {
  email?: string;
  notes: NoteSummary[];
  loading: boolean;
  onOpenNote: (note: NoteSummary) => void;
  onSignOut?: () => void;
  onToggleSidebar?: () => void;
  sidebarCollapsed?: boolean;
};

function snippet(markdown: string): string {
  const text = markdown.replace(/\s+/g, " ").trim();
  if (!text) return "Empty note";
  return text.length > 160 ? `${text.slice(0, 160)}…` : text;
}

export function ProfilePage({
  email,
  notes,
  loading,
  onOpenNote,
  onSignOut,
  onToggleSidebar,
  sidebarCollapsed,
}: Props) {
  const groups = useMemo(() => {
    const map = new Map<string, { name: string; notes: NoteSummary[] }>();
    for (const note of notes) {
      const existing = map.get(note.session_id);
      if (existing) {
        existing.notes.push(note);
      } else {
        map.set(note.session_id, { name: note.session_name, notes: [note] });
      }
    }
    return [...map.values()];
  }, [notes]);

  return (
    <main className="profile">
      <div className="profile-header">
        {onToggleSidebar && (
          <button className="btn menu-btn" type="button" onClick={onToggleSidebar}>
            {sidebarCollapsed ? "Threads" : "Hide threads"}
          </button>
        )}
        <h2>Profile</h2>
        <p className="user-email">{email || "Signed in"}</p>
        {onSignOut && (
          <button className="btn" type="button" onClick={onSignOut}>
            Sign out
          </button>
        )}
      </div>
      {loading && <div className="empty">Loading notes…</div>}
      {!loading && !notes.length && (
        <div className="empty">No notes yet. Generate or write notes in a chat.</div>
      )}
      {groups.map((group) => (
        <section key={group.notes[0].session_id} className="profile-thread">
          <h3>{group.name}</h3>
          <ul>
            {group.notes.map((note) => (
              <li key={note.id}>
                <button className="profile-note" onClick={() => onOpenNote(note)}>
                  <strong>{note.title}</strong>
                  <span>{snippet(note.markdown)}</span>
                  <small>{new Date(note.updated_at).toLocaleString()}</small>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </main>
  );
}
