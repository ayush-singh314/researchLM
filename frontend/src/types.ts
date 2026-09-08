export type Session = {
  id: string;
  name: string;
  created_at: string;
  is_named: boolean;
};

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  turn?: number | null;
};

export type Note = {
  id: string;
  session_id: string;
  title: string;
  markdown: string;
  structured_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type NoteSummary = Note & {
  session_name: string;
};

export type IngestResult = {
  added: string[];
  errors: string[];
};
