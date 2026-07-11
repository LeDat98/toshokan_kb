import { useEffect, useRef, useState } from "react";
import { Icon } from "../icons";
import { PathChip } from "../components/PathChip";
import { TracePanel } from "../components/TracePanel";
import { useToast } from "../components/Toast";
import {
  SAMPLES,
  TRACES,
  type QueryId,
  type Trace,
} from "../data/mock";
import {
  actionBtnStyle,
  answerCardStyle,
  badge,
  iconBtnStyle,
  sectionLabelStyle,
} from "../ui";

const SAMPLE_BADGES = {
  Lookup: badge("var(--accent)", "var(--accent-weak)"),
  Synthesis: badge("var(--info)", "var(--info-weak)"),
  Explore: badge("var(--ink-muted)", "var(--surface-sunk)"),
} as const;

interface AskProps {
  dark: boolean;
  goLibrary: () => void;
  goIngest: () => void;
}

export function Ask({ dark, goLibrary, goIngest }: AskProps) {
  const toast = useToast();
  const [show, setShow] = useState<Record<QueryId, boolean>>({ lookup: false, synthesis: false, notfound: false });
  const [answered, setAnswered] = useState<Record<QueryId, boolean>>({ lookup: false, synthesis: false, notfound: false });
  const [active, setActive] = useState<QueryId | null>(null);
  const [reveal, setReveal] = useState(0);
  const [phase, setPhase] = useState<"idle" | "walking" | "done">("idle");
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [traceOpen, setTraceOpen] = useState(true);
  const timer = useRef<number | undefined>(undefined);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  const totalOf = (tr: Trace) =>
    tr.mode === "linear" ? tr.steps.length : tr.branches.reduce((a, b) => a + b.steps.length, 0);

  const run = (id: QueryId) => () => {
    window.clearTimeout(timer.current);
    const tr = TRACES[id];
    const total = totalOf(tr);
    setShow((s) => ({ ...s, [id]: true }));
    setAnswered((s) => ({ ...s, [id]: false }));
    setActive(id);
    setReveal(0);
    setPhase("walking");
    setTraceOpen(true);
    const tick = (n: number) => {
      if (n > total) {
        setPhase("done");
        setAnswered((s) => ({ ...s, [id]: true }));
        toast(
          `Walk complete · ${tr.terminal.kind === "found" ? "FOUND" : "NOT FOUND"}`,
          tr.terminal.kind === "found" ? "check" : "alert",
        );
        return;
      }
      setReveal(n);
      const last = tr.mode === "linear" ? tr.steps[n - 1] : null;
      const delay = last && (last.kind === "page" || last.kind === "book") ? 620 : 380;
      timer.current = window.setTimeout(() => tick(n + 1), n === total ? 520 : delay);
    };
    timer.current = window.setTimeout(() => tick(1), 260);
  };

  const stopWalk = () => {
    window.clearTimeout(timer.current);
    setPhase("done");
    if (active) setAnswered((s) => ({ ...s, [active]: true }));
  };

  const anyShown = show.lookup || show.synthesis || show.notfound;
  const trace = active ? TRACES[active] : null;

  return (
    <div style={{ height: "100%", display: "flex", minWidth: 0, position: "relative" }}>
      <section style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", position: "relative" }}>
        <div ref={scroller} style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "28px 32px 8px" }}>
          <div style={{ maxWidth: 720, margin: "0 auto", display: "flex", flexDirection: "column", gap: 26 }}>
            {!anyShown && (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  textAlign: "center",
                  padding: "56px 0 30px",
                  animation: "fadeUp .5s ease both",
                }}
              >
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
                    <div
                      key={i}
                      style={{
                        width: s.w,
                        height: s.h,
                        background: s.c,
                        borderRadius: "2px 2px 0 0",
                        opacity: s.o,
                        transform: s.sk ? `skewX(${s.sk}deg)` : undefined,
                      }}
                    />
                  ))}
                </div>
                <div style={{ fontFamily: "var(--serif)", fontSize: 30, fontWeight: 600, letterSpacing: -0.4 }}>
                  The library is open
                </div>
                <p style={{ maxWidth: 430, color: "var(--ink-muted)", fontSize: 14, lineHeight: 1.6, margin: "16px 0 24px" }}>
                  Ask a question and watch the librarian walk the stacks — every answer carries the exact path it
                  walked, or says honestly when the shelf is empty.
                </p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10, justifyContent: "center", maxWidth: 560 }}>
                  {SAMPLES.map((s) => (
                    <button
                      key={s.id}
                      onClick={run(s.id)}
                      className="h-border-accent h-raise"
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 9,
                        padding: "10px 14px",
                        background: "var(--surface-raised)",
                        border: "1px solid var(--border-strong)",
                        borderRadius: 11,
                        cursor: "pointer",
                        boxShadow: "var(--shadow-sm)",
                        textAlign: "left",
                        transition: "transform .12s, border-color .12s",
                      }}
                    >
                      <span style={SAMPLE_BADGES[s.tag]}>{s.tag}</span>
                      <span style={{ fontSize: 13.5, color: "var(--ink)" }}>{s.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {show.lookup && (
              <Exchange query="What is reranking in RAG?">
                {answered.lookup && (
                  <div style={answerCardStyle}>
                    <AnswerHeader type="Lookup" meta="4.2s · 7 hops" />
                    <div style={{ fontSize: 14.5, lineHeight: 1.68, color: "var(--ink)" }}>
                      <p style={{ margin: "0 0 12px" }}>
                        <strong>Reranking</strong> is a second retrieval stage: after the vector search returns a
                        coarse candidate set, a <strong>cross-encoder</strong> re-scores each{" "}
                        <span style={{ fontFamily: "var(--mono)", fontSize: 12.5, background: "var(--surface-sunk)", padding: "1px 5px", borderRadius: 4 }}>
                          (query, passage)
                        </span>{" "}
                        pair jointly, then keeps the true top-k. It trades a little latency for markedly higher
                        precision at the top of the list.
                      </p>
                      <div
                        style={{
                          background: "var(--surface-sunk)",
                          border: "1px solid var(--border)",
                          borderRadius: 10,
                          padding: "13px 15px",
                          fontFamily: "var(--mono)",
                          fontSize: 12.5,
                          lineHeight: 1.7,
                          overflowX: "auto",
                          margin: "0 0 4px",
                        }}
                      >
                        <span style={{ color: "var(--ink-faint)" }}># rerank candidates with a cross-encoder</span>
                        <br />
                        scores = cross_encoder.predict(
                        <br />
                        &nbsp;&nbsp;[(query, doc) <span style={{ color: "var(--accent)" }}>for</span> doc{" "}
                        <span style={{ color: "var(--accent)" }}>in</span> candidates]
                        <br />)
                        <br />
                        ranked = sort_by(scores, desc=<span style={{ color: "var(--info)" }}>True</span>)[:top_k]
                      </div>
                    </div>
                    <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
                      <div style={{ ...sectionLabelStyle, letterSpacing: ".06em", marginBottom: 9 }}>Citation</div>
                      <PathChip
                        hover
                        onClick={() => {
                          goLibrary();
                          toast("Opening AI ▸ RAG ▸ p.12", "book");
                        }}
                        title="Open at p.12 — hover for the matched quote"
                        segs={[
                          { kind: "domain", label: "AI", dot: true },
                          { kind: "shelf", label: "RAG", dot: true },
                          { kind: "book", label: "Advanced RAG Techniques", dot: true },
                          { kind: "page", label: "p.12 Reranking", pageIcon: true },
                        ]}
                        trailing={<span style={{ ...badge("var(--success)", "var(--success-weak)"), marginLeft: 4 }}>High</span>}
                      />
                      <div
                        style={{
                          marginTop: 9,
                          fontSize: 12.5,
                          fontStyle: "italic",
                          color: "var(--ink-muted)",
                          fontFamily: "var(--serif)",
                          paddingLeft: 2,
                        }}
                      >
                        “…a cross-encoder that jointly scores (query, passage) pairs — higher precision at top-k than
                        bi-encoder similarity alone.”
                      </div>
                    </div>
                    <AnswerActions onReask={run("synthesis")} />
                  </div>
                )}
              </Exchange>
            )}

            {show.synthesis && (
              <Exchange query="Compare chunking strategies for technical documents">
                {answered.synthesis && (
                  <div style={answerCardStyle}>
                    <AnswerHeader type="Synthesis" meta="9.4s · 11 hops" tight />
                    <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 12, color: "var(--ink-muted)", marginBottom: 14 }}>
                      <span style={{ color: "var(--info)" }}>
                        <Icon name="sparkle" size={14} />
                      </span>
                      <span>
                        coverage: <strong style={{ color: "var(--ink)" }}>4 / 5</strong> shelves scanned across 3
                        branches
                      </span>
                    </div>
                    <div style={{ display: "flex", flexDirection: "column", gap: 15 }}>
                      {[
                        { book: "RAG Fundamentals", shelf: "RAG", text: "Fixed-size / sliding-window chunking is cheapest and most predictable — but it slices tables and code mid-structure, hurting retrieval on technical docs." },
                        { book: "Advanced RAG Techniques", shelf: "RAG", text: "Semantic / recursive splitting keeps coherent ideas together and adapts chunk size to content boundaries — best recall on prose-heavy technical writing." },
                        { book: "Document Structure", shelf: "NLP", text: "Layout-aware chunking (headings, tables, code fences) wins for structured manuals — pairs well with semantic splitting as a preprocessing pass." },
                      ].map((s) => (
                        <div key={s.book}>
                          <PathChip
                            small
                            segs={[
                              { kind: "shelf", label: s.shelf, dot: true },
                              { kind: "book", label: s.book, dot: true },
                            ]}
                          />
                          <p style={{ margin: "8px 0 0", fontSize: 14, lineHeight: 1.62 }}>{s.text}</p>
                        </div>
                      ))}
                    </div>
                    <AnswerActions borderTop />
                  </div>
                )}
              </Exchange>
            )}

            {show.notfound && (
              <Exchange query="What is quantum error correction?">
                {answered.notfound && (
                  <div
                    style={{
                      background: "var(--surface-raised)",
                      border: "1px solid var(--border)",
                      borderLeft: "3px solid var(--warning)",
                      borderRadius: 14,
                      padding: "20px 22px",
                      boxShadow: "var(--shadow-sm)",
                      animation: "fadeUp .4s ease both",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span
                        style={{
                          flex: "none",
                          width: 40,
                          height: 40,
                          borderRadius: 10,
                          background: "var(--warning-weak)",
                          color: "var(--warning)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                        }}
                      >
                        <Icon name="shelf" size={20} />
                      </span>
                      <div>
                        <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 16 }}>
                          The library doesn't hold this yet
                        </div>
                        <div style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 13.5, color: "var(--ink-muted)" }}>
                          The librarian won't guess.
                        </div>
                      </div>
                      <span style={{ flex: 1 }} />
                      <span style={badge("var(--warning)", "var(--warning-weak)")}>
                        <Icon name="alert" size={13} />
                        NOT FOUND
                      </span>
                    </div>
                    <p style={{ margin: "15px 0 10px", fontSize: 14, lineHeight: 1.6, color: "var(--ink-muted)" }}>
                      The librarian walked the AI hall and scanned two shelves but found nothing catalogued on quantum
                      error correction. Rather than guess, here are the closest shelves:
                    </p>
                    <div style={{ ...sectionLabelStyle, letterSpacing: ".06em", margin: "12px 0 8px" }}>
                      Closest shelves
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      <PathChip hover onClick={goLibrary} segs={[{ kind: "domain", label: "AI", dot: true }, { kind: "shelf", label: "ML", dot: true }]} />
                      <PathChip hover onClick={goLibrary} segs={[{ kind: "domain", label: "AI", dot: true }, { kind: "shelf", label: "Math for AI", dot: true }]} />
                    </div>
                    <button
                      className="h-accent-deep"
                      onClick={() => {
                        goIngest();
                        toast("Topic prefilled in Ingest", "inboxplus");
                      }}
                      style={{
                        marginTop: 18,
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 8,
                        padding: "10px 16px",
                        background: "var(--accent)",
                        color: "var(--accent-ink)",
                        border: 0,
                        borderRadius: 10,
                        fontSize: 13.5,
                        fontWeight: 600,
                        cursor: "pointer",
                        boxShadow: "var(--shadow-sm)",
                      }}
                    >
                      <Icon name="inboxplus" size={16} />
                      Ingest a document about this
                    </button>
                  </div>
                )}
              </Exchange>
            )}
          </div>
        </div>

        <div style={{ flex: "none", padding: "12px 32px 20px", background: "linear-gradient(to top, var(--surface) 70%, transparent)" }}>
          <div
            style={{
              maxWidth: 720,
              margin: "0 auto",
              position: "relative",
              background: "var(--surface-raised)",
              border: "1px solid var(--border-strong)",
              borderRadius: 15,
              boxShadow: "var(--shadow-md)",
              padding: "12px 14px 10px",
            }}
          >
            <textarea
              placeholder="Ask the library…"
              rows={1}
              style={{
                width: "100%",
                border: 0,
                background: "transparent",
                outline: "none",
                resize: "none",
                fontSize: 14.5,
                lineHeight: 1.5,
                color: "var(--ink)",
                minHeight: 24,
              }}
            />
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
              <span style={badge("var(--ink-muted)", "var(--surface-sunk)")}>
                <Icon name="sparkle" size={12} />
                auto · lookup
              </span>
              <span style={{ flex: 1 }} />
              {phase === "walking" ? (
                <button
                  onClick={stopWalk}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 7,
                    height: 36,
                    padding: "0 14px",
                    background: "var(--danger-weak)",
                    color: "var(--danger)",
                    border: "1px solid var(--border)",
                    borderRadius: 10,
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  <Icon name="stop" size={13} />
                  Stop
                </button>
              ) : (
                <button
                  className="h-accent-deep"
                  onClick={() => toast("Type a question, or tap a sample below", "ask")}
                  title="Send"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    width: 38,
                    height: 38,
                    background: "var(--accent)",
                    color: "var(--accent-ink)",
                    border: 0,
                    borderRadius: 10,
                    cursor: "pointer",
                    boxShadow: "var(--shadow-sm)",
                  }}
                >
                  <Icon name="send" size={16} />
                </button>
              )}
            </div>
          </div>
        </div>
      </section>

      {traceOpen ? (
        <TracePanel
          trace={trace}
          reveal={reveal}
          walking={phase === "walking"}
          dark={dark}
          expanded={expanded}
          onToggleStep={(i) => setExpanded((e) => ({ ...e, [i]: !e[i] }))}
          onCollapse={() => setTraceOpen(false)}
        />
      ) : (
        <button
          onClick={() => setTraceOpen(true)}
          title="Show the walk"
          style={{
            position: "absolute",
            top: 16,
            right: 16,
            display: "flex",
            alignItems: "center",
            gap: 8,
            height: 38,
            padding: "0 14px",
            background: "var(--surface-raised)",
            border: "1px solid var(--border-strong)",
            borderRadius: 20,
            boxShadow: "var(--shadow-md)",
            cursor: "pointer",
            color: "var(--walk)",
            fontSize: 13,
            fontWeight: 600,
          }}
        >
          <Icon name="foot" size={18} />
          <span style={{ color: "var(--ink)" }}>Show walk</span>
        </button>
      )}
    </div>
  );
}

function Exchange({ query, children }: { query: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16, animation: "fadeUp .35s ease both" }}>
      <div
        style={{
          alignSelf: "flex-end",
          maxWidth: "74%",
          background: "var(--accent)",
          color: "var(--accent-ink)",
          padding: "11px 15px",
          borderRadius: "14px 14px 4px 14px",
          fontSize: 14,
          lineHeight: 1.5,
          boxShadow: "var(--shadow-sm)",
        }}
      >
        {query}
      </div>
      {children}
    </div>
  );
}

function AnswerHeader({ type, meta, tight }: { type: "Lookup" | "Synthesis"; meta: string; tight?: boolean }) {
  const style = type === "Lookup" ? badge("var(--accent)", "var(--accent-weak)") : badge("var(--info)", "var(--info-weak)");
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: tight ? 6 : 14 }}>
      <span
        style={{
          flex: "none",
          width: 30,
          height: 30,
          borderRadius: 8,
          background: "var(--accent-weak)",
          color: "var(--accent)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Icon name="owl" size={18} />
      </span>
      <span style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 14.5 }}>Librarian</span>
      <span style={style}>
        <Icon name={type === "Lookup" ? "search" : "sparkle"} size={type === "Lookup" ? 12 : 13} />
        {type}
      </span>
      <span style={{ flex: 1 }} />
      <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-faint)" }}>{meta}</span>
    </div>
  );
}

function AnswerActions({ onReask, borderTop }: { onReask?: () => void; borderTop?: boolean }) {
  const toast = useToast();
  return (
    <div
      style={{
        display: "flex",
        gap: 6,
        marginTop: 16,
        ...(borderTop ? { paddingTop: 14, borderTop: "1px solid var(--border)" } : {}),
      }}
    >
      <button onClick={() => toast("Answer copied", "copy")} style={actionBtnStyle}>
        <Icon name="copy" size={14} />
        Copy
      </button>
      {onReask && (
        <button onClick={onReask} style={actionBtnStyle}>
          <Icon name="sparkle" size={14} />
          Re-ask deeper
        </button>
      )}
      <span style={{ flex: 1 }} />
      <button onClick={() => toast("Thanks — logged to trajectories", "thumbup")} title="Helpful" style={iconBtnStyle}>
        <Icon name="thumbup" size={15} />
      </button>
      <button onClick={() => toast("Noted — logged for review", "thumbdown")} title="Not helpful" style={iconBtnStyle}>
        <Icon name="thumbdown" size={15} />
      </button>
    </div>
  );
}
