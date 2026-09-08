import { memo, useEffect, useState, type RefObject } from "react";
import { ChatMarkdown } from "./ChatMarkdown";
import type { ChatMessage } from "./types";

const THINKING_PHASES = [
  "Searching your papers",
  "Reading sources",
  "Thinking",
];

type Props = {
  messages: ChatMessage[];
  streaming: string;
  thinking: boolean;
  messagesLoading: boolean;
  bottomRef: RefObject<HTMLDivElement | null>;
};

export function ThinkingDots() {
  return (
    <span className="thinking-dots" aria-hidden="true">
      <span>.</span>
      <span>.</span>
      <span>.</span>
    </span>
  );
}

export const ChatPane = memo(function ChatPane({
  messages,
  streaming,
  thinking,
  messagesLoading,
  bottomRef,
}: Props) {
  const [phase, setPhase] = useState(0);
  const showThinking = thinking && !streaming;

  useEffect(() => {
    if (!showThinking) {
      setPhase(0);
      return;
    }
    const id = window.setInterval(() => {
      setPhase((current) => (current + 1) % THINKING_PHASES.length);
    }, 2400);
    return () => window.clearInterval(id);
  }, [showThinking]);

  return (
    <div className="messages">
      {messagesLoading && !messages.length && !streaming && !thinking && (
        <div className="empty">Loading conversation…</div>
      )}
      {!messagesLoading && !messages.length && !streaming && !thinking && (
        <div className="empty">Ask a question about your papers. Add a URL or PDF to get started.</div>
      )}
      {messages.map((msg, index) => (
        <div key={`${msg.role}-${index}`} className={`bubble ${msg.role}`}>
          <div className="role">{msg.role === "user" ? "You" : "Researcher"}</div>
          <ChatMarkdown content={msg.content} showCopy={msg.role === "assistant"} />
        </div>
      ))}
      {showThinking && (
        <div className="bubble assistant thinking" aria-live="polite" aria-busy="true">
          <div className="role">Researcher</div>
          <div className="thinking-line">
            {THINKING_PHASES[phase]}
            <ThinkingDots />
          </div>
        </div>
      )}
      {streaming && (
        <div className="bubble assistant">
          <div className="role">Researcher</div>
          <div className="stream-plain">
            {streaming}
            <span className="stream-caret" aria-hidden="true" />
          </div>
        </div>
      )}
      <div ref={bottomRef} />
    </div>
  );
});
