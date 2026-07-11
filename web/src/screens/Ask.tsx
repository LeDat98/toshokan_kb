import { useEffect, useRef, useState } from "react";
import { Icon } from "../icons";
import { PathChip, type PathSeg } from "../components/PathChip";
import { TracePanel } from "../components/TracePanel";
import { useToast } from "../components/Toast";
import { streamQuery, type AnswerPayload, type StepEvent } from "../api";
import { actionBtnStyle, answerCardStyle, badge, iconBtnStyle, sectionLabelStyle } from "../ui";

interface Exchange {
  id: string;
  query: string;
  steps: StepEvent[];
  answer: AnswerPayload | null;
  running: boolean;
  error?: string;
}

const SAMPLES = [
  { tag: "Lookup", label: "What is reranking in RAG?", badge: badge("var(--accent)", "var(--accent-weak)") },
  { tag: "Compare", label: "How do chunking strategies differ?", badge: badge("var(--info)", "var(--info-weak)") },
  { tag: "Explore", label: "What is quantum error correction?", badge: badge("var(--ink-muted)", "var(--surface-sunk)") },
];

interface AskProps {
  dark: boolean;
  goLibrary: () => void;
  goIngest: () => void;
}

const KIND_ORDER = ["domain", "shelf", "book", "page"] as const;

function pathToSegs(path: string): PathSeg[] {
  const parts = path.split(" ▸ ").filter(Boolean);
  return parts.map((label, i) => {
    const kind = (KIND_ORDER[Math.min(i, KIND_ORDER.length - 1)] ??
      "page") as PathSeg["kind"];
    const last = i === parts.length - 1;
    return { kind, label, dot: !last, pageIcon: last };
  });
}

export function Ask({ dark, goLibrary, goIngest }: AskProps) {
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [input, setInput] = useState("");
  const [traceOpen, setTraceOpen] = useState(true);
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const abortRef = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const active = exchanges.length ? exchanges[exchanges.length - 1] : null;
  const running = active?.running ?? false;

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [exchanges]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const patch = (id: string, fn: (e: Exchange) => Exchange) =>
    setExchanges((prev) => prev.map((e) => (e.id === id ? fn(e) : e)));

  const send = (q: string) => {
    q = q.trim();
    if (!q || running) return;
    const id = crypto.randomUUID();
    setExchanges((prev) => [...prev, { id, query: q, steps: [], answer: null, running: true }]);
    setInput("");
    setExpanded({});
    setTraceOpen(true);
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    streamQuery(
      q,
      {
        onNav: (ev) => patch(id, (e) => ({ ...e, steps: [...e.steps, ev] })),
        onAnswer: (a) => patch(id, (e) => ({ ...e, answer: a })),
        onError: (m) => patch(id, (e) => ({ ...e, error: m })),
        onDone: () => patch(id, (e) => ({ ...e, running: false })),
      },
      ctrl.signal,
    ).catch(() => patch(id, (e) => ({ ...e, running: false, error: "connection lost" })));
  };

  const stop = () => {
    abortRef.current?.abort();
    if (active) patch(active.id, (e) => ({ ...e, running: false }));
  };

  return (
    <div style={{ height: "100%", display: "flex", minWidth: 0, position: "relative" }}>
      <section style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", position: "relative" }}>
        <div ref={scroller} style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "28px 32px 8px" }}>
          <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", flexDirection: "column", gap: 26 }}>
            {exchanges.length === 0 && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: "56px 0 30px", animation: "fadeUp .5s ease both" }}>
                <div style={{ display: "flex", alignItems: "flex-end", gap: 5, height: 96, marginBottom: 26, animation: "floaty 6s ease-in-out infinite" }}>
                  {[
                    { w: 15, h: 64, c: "var(--domain)", o: 0.85, sk: -4 },
                    { w: 13, h: 82, c: "var(--shelf)", o: 0.9, sk: 0 },
                    { w: 17, h: 52, c: "var(--book)", o: 0.8, sk: 3 },
                    { w: 12, h: 74, c: "var(--accent)", o: 1, sk: 0 },
                    { w: 16, h: 90, c: "var(--page)", o: 0.85, sk: -3 },
                    { w: 13, h: 60, c: "var(--walk)", o: 0.9, sk: 0 },
                    { w: 15, h: 78, c: "var(--domain)", o: 0.7, sk: 0 },
                  ].map((s, i) => (
                    <div key={i} style={{ width: s.w, height: s.h, background: s.c, borderRadius: "2px 2px 0 0", opacity: s.o, transform: s.sk ? `skewX(${s.sk}deg)` : undefined }} />
                  ))}
                </div>
                <div style={{ fontFamily: "var(--serif)", fontSize: 30, fontWeight: 600, letterSpacing: -0.4 }}>The library is open</div>
                <p style={{ maxWidth: 430, color: "var(--ink-muted)", fontSize: 14, lineHeight: 1.6, margin: "16px 0 24px" }}>
                  Ask a question and watch the librarian walk the stacks — every answer carries the exact path it walked, or says honestly when the shelf is empty.
                </p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10, justifyContent: "center", maxWidth: 560 }}>
                  {SAMPLES.map((s) => (
                    <button key={s.label} onClick={() => send(s.label)} className="h-border-accent h-raise" style={{ display: "flex", alignItems: "center", gap: 9, padding: "10px 14px", background: "var(--surface-raised)", border: "1px solid var(--border-strong)", borderRadius: 11, cursor: "pointer", boxShadow: "var(--shadow-sm)", textAlign: "left", transition: "transform .12s, border-color .12s" }}>
                      <span style={s.badge}>{s.tag}</span>
                      <span style={{ fontSize: 13.5, color: "var(--ink)" }}>{s.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {exchanges.map((ex) => (
              <div key={ex.id} style={{ display: "flex", flexDirection: "column", gap: 16, animation: "fadeUp .35s ease both" }}>
                <div style={{ alignSelf: "flex-end", maxWidth: "74%", background: "var(--accent)", color: "var(--accent-ink)", padding: "11px 15px", borderRadius: "14px 14px 4px 14px", fontSize: 14, lineHeight: 1.5, boxShadow: "var(--shadow-sm)" }}>
                  {ex.query}
                </div>
                {ex.running && !ex.answer && (
                  <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--ink-muted)", fontSize: 13.5, fontStyle: "italic", fontFamily: "var(--serif)", padding: "4px 2px" }}>
                    <span style={{ color: "var(--walk)" }}>
                      <Icon name="foot" size={16} />
                    </span>
                    The librarian is walking the stacks…
                  </div>
                )}
                {ex.answer && <AnswerCard ex={ex} onLibrary={goLibrary} onIngest={goIngest} />}
                {ex.error && !ex.answer && (
                  <div style={{ padding: "12px 15px", background: "var(--danger-weak)", border: "1px solid var(--border)", borderLeft: "3px solid var(--danger)", borderRadius: 12, color: "var(--danger)", fontSize: 13.5 }}>
                    Couldn't reach the librarian: {ex.error}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div style={{ flex: "none", padding: "12px 32px 20px", background: "linear-gradient(to top, var(--surface) 70%, transparent)" }}>
          <div style={{ maxWidth: 720, margin: "0 auto", position: "relative", background: "var(--surface-raised)", border: "1px solid var(--border-strong)", borderRadius: 15, boxShadow: "var(--shadow-md)", padding: "12px 14px 10px" }}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder="Ask the library…"
              rows={1}
              style={{ width: "100%", border: 0, background: "transparent", outline: "none", resize: "none", fontSize: 14.5, lineHeight: 1.5, color: "var(--ink)", minHeight: 24 }}
            />
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
              <span style={badge("var(--ink-muted)", "var(--surface-sunk)")}>
                <Icon name="foot" size={12} />
                walks the real library
              </span>
              <span style={{ flex: 1 }} />
              {running ? (
                <button onClick={stop} style={{ display: "flex", alignItems: "center", gap: 7, height: 36, padding: "0 14px", background: "var(--danger-weak)", color: "var(--danger)", border: "1px solid var(--border)", borderRadius: 10, fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
                  <Icon name="stop" size={13} />
                  Stop
                </button>
              ) : (
                <button onClick={() => send(input)} className="h-accent-deep" title="Send" style={{ display: "flex", alignItems: "center", justifyContent: "center", width: 38, height: 38, background: "var(--accent)", color: "var(--accent-ink)", border: 0, borderRadius: 10, cursor: "pointer", boxShadow: "var(--shadow-sm)" }}>
                  <Icon name="send" size={16} />
                </button>
              )}
            </div>
          </div>
        </div>
      </section>

      {traceOpen ? (
        <TracePanel
          steps={active?.steps ?? []}
          running={running}
          idle={exchanges.length === 0}
          dark={dark}
          expanded={expanded}
          onToggleStep={(i) => setExpanded((e) => ({ ...e, [i]: !e[i] }))}
          onCollapse={() => setTraceOpen(false)}
        />
      ) : (
        <button onClick={() => setTraceOpen(true)} title="Show the walk" style={{ position: "absolute", top: 16, right: 16, display: "flex", alignItems: "center", gap: 8, height: 38, padding: "0 14px", background: "var(--surface-raised)", border: "1px solid var(--border-strong)", borderRadius: 20, boxShadow: "var(--shadow-md)", cursor: "pointer", color: "var(--walk)", fontSize: 13, fontWeight: 600 }}>
          <Icon name="foot" size={18} />
          <span style={{ color: "var(--ink)" }}>Show walk</span>
        </button>
      )}
    </div>
  );
}

function AnswerCard({ ex, onLibrary, onIngest }: { ex: Exchange; onLibrary: () => void; onIngest: () => void }) {
  const toast = useToast();
  const a = ex.answer!;
  const notFound = a.status === "not_found";
  const meta = `${a.hops} hops${a.backtracks ? ` · ${a.backtracks} backtracks` : ""}`;

  if (notFound) {
    return (
      <div style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderLeft: "3px solid var(--warning)", borderRadius: 14, padding: "20px 22px", boxShadow: "var(--shadow-sm)", animation: "fadeUp .4s ease both" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ flex: "none", width: 40, height: 40, borderRadius: 10, background: "var(--warning-weak)", color: "var(--warning)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Icon name="shelf" size={20} />
          </span>
          <div>
            <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 16 }}>The library doesn't hold this yet</div>
            <div style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 13.5, color: "var(--ink-muted)" }}>The librarian won't guess.</div>
          </div>
          <span style={{ flex: 1 }} />
          <span style={badge("var(--warning)", "var(--warning-weak)")}>
            <Icon name="alert" size={13} />
            NOT FOUND
          </span>
        </div>
        <p style={{ margin: "15px 0 10px", fontSize: 14, lineHeight: 1.6, color: "var(--ink-muted)", whiteSpace: "pre-wrap" }}>{a.text}</p>
        {a.closest.length > 0 && (
          <>
            <div style={{ ...sectionLabelStyle, letterSpacing: ".06em", margin: "12px 0 8px" }}>Closest shelves</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {a.closest.map((c) => (
                <PathChip key={c} hover onClick={onLibrary} segs={pathToSegs(c)} />
              ))}
            </div>
          </>
        )}
        <button onClick={onIngest} className="h-accent-deep" style={{ marginTop: 18, display: "inline-flex", alignItems: "center", gap: 8, padding: "10px 16px", background: "var(--accent)", color: "var(--accent-ink)", border: 0, borderRadius: 10, fontSize: 13.5, fontWeight: 600, cursor: "pointer", boxShadow: "var(--shadow-sm)" }}>
          <Icon name="inboxplus" size={16} />
          Ingest a document about this
        </button>
      </div>
    );
  }

  return (
    <div style={answerCardStyle}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <span style={{ flex: "none", width: 30, height: 30, borderRadius: 8, background: "var(--accent-weak)", color: "var(--accent)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <Icon name="owl" size={18} />
        </span>
        <span style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 14.5 }}>Librarian</span>
        <span style={badge(a.confidence === "high" ? "var(--success)" : a.confidence === "low" ? "var(--warning)" : "var(--accent)", a.confidence === "high" ? "var(--success-weak)" : a.confidence === "low" ? "var(--warning-weak)" : "var(--accent-weak)")}>
          {a.confidence} confidence
        </span>
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-faint)" }}>{meta}</span>
      </div>
      <div style={{ fontSize: 14.5, lineHeight: 1.68, color: "var(--ink)" }}>
        {a.text.split("\n\n").map((para, i) => (
          <p key={i} style={{ margin: i ? "12px 0 0" : 0, whiteSpace: "pre-wrap" }}>
            {para}
          </p>
        ))}
      </div>
      {a.citations.length > 0 && (
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
          <div style={{ ...sectionLabelStyle, letterSpacing: ".06em", marginBottom: 9 }}>
            {a.citations.length > 1 ? "Citations" : "Citation"}
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {a.citations.map((c) => (
              <PathChip key={c.page_id} hover onClick={onLibrary} title="Open in the library" segs={pathToSegs(c.path)} />
            ))}
          </div>
        </div>
      )}
      <div style={{ display: "flex", gap: 6, marginTop: 16 }}>
        <button onClick={() => { navigator.clipboard?.writeText(a.text); toast("Answer copied", "copy"); }} style={actionBtnStyle}>
          <Icon name="copy" size={14} />
          Copy
        </button>
        <span style={{ flex: 1 }} />
        <button onClick={() => toast("Thanks — logged", "thumbup")} title="Helpful" style={iconBtnStyle}>
          <Icon name="thumbup" size={15} />
        </button>
        <button onClick={() => toast("Noted — logged for review", "thumbdown")} title="Not helpful" style={iconBtnStyle}>
          <Icon name="thumbdown" size={15} />
        </button>
      </div>
    </div>
  );
}
