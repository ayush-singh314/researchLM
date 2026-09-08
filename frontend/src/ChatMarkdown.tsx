import { useEffect, useRef, useState, type ComponentProps } from "react";
import Markdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

type CodeProps = ComponentProps<"code"> & { inline?: boolean };

function MermaidBlock({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setFailed(false);
    import("mermaid")
      .then((mod) => {
        const mermaid = mod.default;
        mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "neutral" });
        const id = `mmd-${Math.random().toString(36).slice(2)}`;
        return mermaid.render(id, chart);
      })
      .then(({ svg }) => {
        if (!cancelled && ref.current) ref.current.innerHTML = svg;
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [chart]);

  if (failed) {
    return (
      <pre>
        <code>{chart}</code>
      </pre>
    );
  }
  return <div className="mermaid-block" ref={ref} />;
}

function convertLatexDelimiters(text: string, open: string, close: string, wrap: (inner: string) => string): string {
  let out = "";
  let i = 0;
  while (i < text.length) {
    if (text.startsWith(open, i)) {
      const start = i + open.length;
      const end = text.indexOf(close, start);
      if (end === -1) {
        out += text.slice(i);
        break;
      }
      out += wrap(text.slice(start, end).trim());
      i = end + close.length;
      continue;
    }
    out += text[i];
    i += 1;
  }
  return out;
}

function prepareMarkdown(raw: string): string {
  let text = raw
    .replace(/[\u00a0\u202f\u2009\u200a]/g, " ")
    .replace(/&nbsp;/gi, " ");

  // Markdown treats \( as escaped "(", so convert before remark parses.
  // Scan for "\)" / "\]" so \left( and \right) stay intact.
  text = convertLatexDelimiters(text, "\\[", "\\]", (inner) => `\n$$\n${inner}\n$$\n`);
  text = convertLatexDelimiters(text, "\\(", "\\)", (inner) => `$${inner}$`);

  // Only wrap a whole parenthetical that is itself a latex command, not \left( / \text(
  text = text.replace(
    /\(\s*(\\(?:displaystyle|frac)[^()\\]*(?:\{[^}]*\}[^()\\]*)*)\)/g,
    (_, body: string) => `$${body.trim()}$`,
  );

  return text;
}

type ChatMarkdownProps = {
  content: string;
  showCopy?: boolean;
};

export function ChatMarkdown({ content, showCopy = false }: ChatMarkdownProps) {
  const [copied, setCopied] = useState(false);
  const source = prepareMarkdown(content);

  async function copy() {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  return (
    <div className="chat-md-wrap">
      <div className="md">
        <Markdown
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[rehypeRaw, rehypeKatex]}
          components={{
            code({ className, children, ...props }: CodeProps) {
              const text = String(children).replace(/\n$/, "");
              if (/language-mermaid/.test(className || "")) {
                return <MermaidBlock chart={text} />;
              }
              return (
                <code className={className} {...props}>
                  {children}
                </code>
              );
            },
          }}
        >
          {source}
        </Markdown>
      </div>
      {showCopy && (
        <button type="button" className="copy-btn" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </button>
      )}
    </div>
  );
}
