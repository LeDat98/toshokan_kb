import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { CSSProperties } from "react";

// Answers arrive as markdown (the librarian writes lists, tables, bold, code). react-markdown does
// NOT render raw HTML unless rehype-raw is added — we deliberately leave it out, so a page that
// smuggled a <script> into the evidence cannot execute here. GFM adds tables, strikethrough, and
// task lists. Everything is styled through the design tokens, so it inherits light/dark for free.

const wrap: CSSProperties = { fontSize: 14.5, lineHeight: 1.68, color: "var(--ink)" };

export function Markdown({ children }: { children: string }) {
  return (
    <div style={wrap}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: (p) => <p style={{ margin: "0 0 10px" }} {...p} />,
          strong: (p) => <strong style={{ fontWeight: 680 }} {...p} />,
          em: (p) => <em {...p} />,
          h1: (p) => <h3 style={hStyle(17)} {...p} />,
          h2: (p) => <h3 style={hStyle(16)} {...p} />,
          h3: (p) => <h3 style={hStyle(15)} {...p} />,
          ul: (p) => <ul style={{ margin: "0 0 10px", paddingLeft: 22 }} {...p} />,
          ol: (p) => <ol style={{ margin: "0 0 10px", paddingLeft: 22 }} {...p} />,
          li: (p) => <li style={{ margin: "3px 0", lineHeight: 1.6 }} {...p} />,
          a: (p) => (
            <a style={{ color: "var(--accent)", textDecoration: "underline", textUnderlineOffset: 2 }} target="_blank" rel="noreferrer noopener" {...p} />
          ),
          blockquote: (p) => (
            <blockquote style={{ margin: "0 0 10px", padding: "6px 14px", borderLeft: "3px solid var(--border-strong)", color: "var(--ink-muted)", fontStyle: "italic" }} {...p} />
          ),
          hr: () => <hr style={{ border: 0, borderTop: "1px solid var(--border)", margin: "14px 0" }} />,
          code: (props) => {
            const { children, className, ...rest } = props as { children?: unknown; className?: string };
            // fenced blocks carry a language class; inline code does not
            if (className) {
              return (
                <code style={{ fontFamily: "var(--mono)", fontSize: 12.5, color: "var(--ink)" }} className={className} {...rest}>
                  {children as never}
                </code>
              );
            }
            return (
              <code style={{ fontFamily: "var(--mono)", fontSize: 12.5, background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 5, padding: "1px 5px" }} {...rest}>
                {children as never}
              </code>
            );
          },
          pre: (p) => (
            <pre style={{ margin: "0 0 10px", padding: "12px 14px", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 10, overflowX: "auto", fontSize: 12.5, lineHeight: 1.55 }} {...p} />
          ),
          table: (p) => (
            <div style={{ overflowX: "auto", margin: "0 0 12px" }}>
              <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }} {...p} />
            </div>
          ),
          th: (p) => <th style={{ textAlign: "left", padding: "7px 10px", borderBottom: "2px solid var(--border-strong)", background: "var(--surface-sunk)", fontWeight: 650, fontSize: 12 }} {...p} />,
          td: (p) => <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)", verticalAlign: "top" }} {...p} />,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

function hStyle(size: number): CSSProperties {
  return { fontFamily: "var(--serif)", fontSize: size, fontWeight: 600, margin: "14px 0 8px", lineHeight: 1.3 };
}
