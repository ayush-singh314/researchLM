import { getAccessToken } from "./auth";
import type { ChatMessage, IngestResult, Note, NoteSummary, Session } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function authHeaders(extra?: HeadersInit): Promise<Headers> {
  const headers = new Headers(extra);
  const token = await getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = await authHeaders(init?.headers);
  const response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      detail = await response.text();
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<{ id: string; email?: string }>("/me"),
  listSessions: () => request<Session[]>("/sessions"),
  createSession: () =>
    request<Session>("/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    }),
  getSession: (id: string) => request<Session>(`/sessions/${id}`),
  renameSession: (id: string, name: string) =>
    request<Session>(`/sessions/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }),
  listDocuments: (id: string) => request<{ titles: string[] }>(`/sessions/${id}/documents`),
  deleteDocument: (id: string, title: string) =>
    request<void>(`/sessions/${id}/documents?title=${encodeURIComponent(title)}`, {
      method: "DELETE",
    }),
  uploadDocuments: async (id: string, files: FileList) => {
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    return request<IngestResult>(`/sessions/${id}/documents`, { method: "POST", body: form });
  },
  loadUrls: (id: string, urls: string[]) =>
    request<IngestResult>(`/sessions/${id}/urls`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ urls }),
    }),
  listMessages: (id: string) => request<ChatMessage[]>(`/sessions/${id}/messages`),
  listAllNotes: (limit = 50) => request<NoteSummary[]>(`/notes?limit=${limit}`),
  listNotes: (id: string) => request<Note[]>(`/sessions/${id}/notes`),
  createNote: (id: string) =>
    request<Note>(`/sessions/${id}/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "Untitled", markdown: "" }),
    }),
  updateNote: (sessionId: string, noteId: string, body: { title?: string; markdown?: string }) =>
    request<Note>(`/sessions/${sessionId}/notes/${noteId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  generateNote: (id: string) =>
    request<Note>(`/sessions/${id}/notes/generate`, { method: "POST" }),
  deleteNote: (sessionId: string, noteId: string) =>
    request<void>(`/sessions/${sessionId}/notes/${noteId}`, { method: "DELETE" }),
};

export async function streamChat(
  sessionId: string,
  message: string,
  onToken: (text: string) => void,
): Promise<{ answer: string; session?: Session }> {
  const headers = await authHeaders({ "Content-Type": "application/json" });
  const response = await fetch(`${API_BASE}/sessions/${sessionId}/chat`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message }),
  });
  if (!response.ok || !response.body) {
    throw new Error("Chat request failed");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let answer = "";
  let session: Session | undefined;
  let eventName = "message";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const lines = part.split("\n");
      let dataLine = "";
      for (const line of lines) {
        if (line.startsWith("event:")) eventName = line.slice(6).trim();
        if (line.startsWith("data:")) dataLine += line.slice(5).trim();
      }
      if (!dataLine) continue;
      const payload = JSON.parse(dataLine);
      if (eventName === "token" && payload.text) {
        answer += payload.text;
        onToken(payload.text);
      }
      if (eventName === "done") {
        answer = payload.answer || answer;
        session = payload.session;
      }
      if (eventName === "error") {
        throw new Error(payload.detail || "Chat failed");
      }
      eventName = "message";
    }
  }
  return { answer, session };
}
