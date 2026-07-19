import { useEffect, useRef, useState } from "react";
import { Icon } from "../icons";
import { PathChip, type PathSeg } from "../components/PathChip";
import { TracePanel } from "../components/TracePanel";
import { Markdown } from "../components/Markdown";
import { ThinkingTimeline } from "../components/ThinkingTimeline";
import { useToast } from "../components/Toast";
import { fetchModels, fetchOptions, fetchPersona, streamQuery, type AnswerPayload, type ModelList, type OptionsInfo, type StepEvent } from "../api";
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
  const [models, setModels] = useState<ModelList | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  // Retrieval / answer dials from the option panel — null = "use the server default" (D-058/D-057).
  const [options, setOptions] = useState<OptionsInfo | null>(null);
  const [depth, setDepth] = useState<string | null>(null);
  const [basket, setBasket] = useState<string | null>(null);
  const [banInvented, setBanInvented] = useState<boolean | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const scroller = useRef<HTMLDivElement>(null);

  const active = exchanges.length ? exchanges[exchanges.length - 1] : null;
  const running = active?.running ?? false;
  const current = model ?? models?.current ?? "…";

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [exchanges]);

  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => {
    fetchModels().then(setModels).catch(() => undefined);
    fetchOptions().then(setOptions).catch(() => undefined);
  }, []);

  // "/model" in the composer opens the picker — the keyboard route to the same menu as the button.
  useEffect(() => {
    if (input.trim().toLowerCase() === "/model") setPickerOpen(true);
  }, [input]);

  const patch = (id: string, fn: (e: Exchange) => Exchange) =>
    setExchanges((prev) => prev.map((e) => (e.id === id ? fn(e) : e)));

  const pick = (name: string) => {
    setModel(name);
    setPickerOpen(false);
    if (input.trim().toLowerCase() === "/model") setInput("");
  };

  const send = (q: string) => {
    q = q.trim();
    if (!q || running) return;
    if (q.toLowerCase() === "/model") {
      setPickerOpen(true);
      return; // a command, not a question — never send it to the librarian
    }
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
      {
        // every dial rides WITH the query — switching reloads nothing (routes.py::_request_settings)
        model: model ?? undefined,
        depth: depth ?? undefined,
        basket: basket ?? undefined,
        ban_invented: banInvented ?? undefined,
      },
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
                {(ex.running || ex.steps.length > 0) && (
                  <ThinkingTimeline
                    steps={ex.steps}
                    running={ex.running}
                    answered={ex.answer?.status === "answered"}
                    notFound={ex.answer?.status === "not_found"}
                    dark={dark}
                  />
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
            {pickerOpen && models && (
              <>
                <div onClick={() => setPickerOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 20 }} />
                <div style={{ position: "absolute", bottom: "calc(100% + 8px)", left: 8, zIndex: 21, minWidth: 320, background: "var(--surface-raised)", border: "1px solid var(--border-strong)", borderRadius: 13, boxShadow: "var(--shadow-lg, var(--shadow-md))", padding: 6, animation: "fadeUp .16s ease both" }}>
                  <div style={{ padding: "6px 10px 8px", fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--ink-muted)" }}>
                    Model — takes effect on the next question
                  </div>
                  {models.models.map((m) => {
                    // The walk needs tool calling, which only Gemini has. Say so BEFORE the pick,
                    // not after a half-finished walk dies (llm/client.py refuses rather than degrade).
                    const walkOnly = !m.tools && models.retrieval_mode !== "cascade";
                    const disabled = !m.available || walkOnly;
                    const selected = m.name === current;
                    return (
                      <button
                        key={m.name}
                        disabled={disabled}
                        onClick={() => pick(m.name)}
                        style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", padding: "9px 10px", background: selected ? "var(--surface-sunk)" : "transparent", border: 0, borderRadius: 9, cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.42 : 1, textAlign: "left" }}
                      >
                        <span style={{ width: 6, height: 6, borderRadius: 3, background: selected ? "var(--accent)" : "transparent", flex: "none" }} />
                        <span style={{ flex: 1, minWidth: 0, fontSize: 13.5, fontWeight: selected ? 650 : 500, color: "var(--ink)" }}>{m.name}</span>
                        <span style={{ fontSize: 11, color: "var(--ink-muted)" }}>
                          {!m.available ? "no API key" : walkOnly ? "no tool calling" : m.provider}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </>
            )}
            {settingsOpen && options && (
              <>
                <div onClick={() => setSettingsOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 20 }} />
                <OptionsPopover
                  options={options}
                  depth={depth}
                  basket={basket}
                  banInvented={banInvented}
                  onDepth={setDepth}
                  onBasket={setBasket}
                  onBan={setBanInvented}
                />
              </>
            )}
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") setPickerOpen(false);
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              placeholder="Ask the library…  (/model to switch)"
              rows={1}
              style={{ width: "100%", border: 0, background: "transparent", outline: "none", resize: "none", fontSize: 14.5, lineHeight: 1.5, color: "var(--ink)", minHeight: 24 }}
            />
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
              <button
                onClick={() => setPickerOpen((v) => !v)}
                title="Switch model (/model)"
                className="h-border-accent"
                style={{ display: "flex", alignItems: "center", gap: 6, height: 26, padding: "0 9px", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 7, cursor: "pointer", fontSize: 11.5, fontWeight: 600, color: "var(--ink-muted)", transition: "border-color .12s" }}
              >
                <Icon name="sparkle" size={11} />
                {current}
              </button>
              <button
                onClick={() => setSettingsOpen((v) => !v)}
                title="Retrieval & answer options"
                className="h-border-accent"
                style={{ display: "flex", alignItems: "center", gap: 6, height: 26, padding: "0 9px", background: settingsOpen ? "var(--accent-weak)" : "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 7, cursor: "pointer", fontSize: 11.5, fontWeight: 600, color: "var(--ink-muted)", transition: "border-color .12s" }}
              >
                <Icon name="settings" size={12} />
                Options
              </button>
              <span style={{ flex: "none" }} />
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

// Reveal the (already-verified) answer with a smooth typewriter feel. The backend does NOT stream
// tokens — it can't, because the anti-fabrication gate (D-057) must see the WHOLE answer before it
// is shown — so this is a client-side reveal of text that is already final and safe. It animates
// exactly ONCE, on mount (the card is keyed by exchange id, so history never re-animates), and
// honours prefers-reduced-motion.
function useReveal(text: string): { shown: string; done: boolean } {
  const reduce =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const [n, setN] = useState(reduce ? text.length : 0);
  useEffect(() => {
    if (reduce) { setN(text.length); return; }
    let cur = 0;
    const total = text.length;
    const step = Math.max(3, Math.round(total / 80)); // reveal in ~80 ticks ≈ 1.3s, faster if short
    const id = window.setInterval(() => {
      cur = Math.min(total, cur + step);
      setN(cur);
      if (cur >= total) window.clearInterval(id);
    }, 16);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return { shown: text.slice(0, n), done: n >= text.length };
}

function Segmented({ label, opts, value, onChange }: { label: string; opts: string[]; value: string; onChange: (v: string) => void }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ ...sectionLabelStyle, letterSpacing: ".05em", marginBottom: 6 }}>{label}</div>
      <div style={{ display: "flex", gap: 4, background: "var(--surface-sunk)", padding: 3, borderRadius: 9 }}>
        {opts.map((o) => {
          const on = o === value;
          return (
            <button
              key={o}
              onClick={() => onChange(o)}
              style={{ flex: 1, padding: "6px 4px", background: on ? "var(--surface-raised)" : "transparent", color: on ? "var(--ink)" : "var(--ink-muted)", border: on ? "1px solid var(--border-strong)" : "1px solid transparent", borderRadius: 7, cursor: "pointer", fontSize: 12, fontWeight: on ? 650 : 500, boxShadow: on ? "var(--shadow-sm)" : "none", textTransform: "capitalize" }}
            >
              {o}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function OptionsPopover({ options, depth, basket, banInvented, onDepth, onBasket, onBan }: {
  options: OptionsInfo;
  depth: string | null; basket: string | null; banInvented: boolean | null;
  onDepth: (v: string) => void; onBasket: (v: string) => void; onBan: (v: boolean) => void;
}) {
  const ban = banInvented ?? options.ban_invented;
  const [behaviorOpen, setBehaviorOpen] = useState(false);
  const [persona, setPersona] = useState<string | null>(null);
  useEffect(() => {
    if (behaviorOpen && persona === null) fetchPersona().then(setPersona).catch(() => setPersona(""));
  }, [behaviorOpen, persona]);
  return (
    <div style={{ position: "absolute", bottom: "calc(100% + 8px)", left: 8, zIndex: 21, width: 320, maxHeight: "70vh", overflowY: "auto", background: "var(--surface-raised)", border: "1px solid var(--border-strong)", borderRadius: 13, boxShadow: "var(--shadow-lg, var(--shadow-md))", padding: "12px 14px", animation: "fadeUp .16s ease both" }}>
      <div style={{ ...sectionLabelStyle, letterSpacing: ".06em", marginBottom: 10 }}>
        Retrieval & answer — next question
      </div>
      <Segmented label="Retrieval depth" opts={options.depth.options} value={depth ?? options.depth.current} onChange={onDepth} />
      <Segmented label="Basket (pages read)" opts={options.basket.options} value={basket ?? options.basket.current} onChange={onBasket} />
      <button
        onClick={() => onBan(!ban)}
        style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", padding: "9px 10px", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 9, cursor: "pointer", textAlign: "left", marginBottom: 10 }}
      >
        <span style={{ width: 34, height: 20, borderRadius: 11, background: ban ? "var(--accent)" : "var(--border-strong)", position: "relative", flex: "none", transition: "background .15s" }}>
          <span style={{ position: "absolute", top: 2, left: ban ? 16 : 2, width: 16, height: 16, borderRadius: 8, background: "var(--surface-raised)", transition: "left .15s", boxShadow: "var(--shadow-sm)" }} />
        </span>
        <span style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ink)" }}>Anti-fabrication</div>
          <div style={{ fontSize: 11, color: "var(--ink-muted)", lineHeight: 1.4 }}>Strip invented numbers not in the sources</div>
        </span>
      </button>
      <div style={{ fontSize: 11, color: "var(--ink-faint)", fontFamily: "var(--mono)", lineHeight: 1.5, paddingTop: 4, borderTop: "1px solid var(--border)" }}>
        auto → window {options.resolved.fetch} · basket {options.resolved.basket}
        {" "}for this {options.corpus_pages}-page library
      </div>
      <button
        onClick={() => setBehaviorOpen((v) => !v)}
        style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", marginTop: 10, padding: "7px 2px", background: "transparent", border: 0, borderTop: "1px solid var(--border)", cursor: "pointer", fontSize: 11.5, fontWeight: 600, color: "var(--ink-muted)" }}
      >
        <Icon name={behaviorOpen ? "moon" : "owl"} size={13} />
        How the librarian behaves
        <span style={{ flex: 1 }} />
        <span style={{ color: "var(--ink-faint)" }}>{behaviorOpen ? "−" : "+"}</span>
      </button>
      {behaviorOpen && (
        <div style={{ fontSize: 12, marginTop: 4, paddingTop: 8, borderTop: "1px dashed var(--border)" }}>
          {persona === null ? (
            <span style={{ color: "var(--ink-faint)" }}>Loading…</span>
          ) : (
            <Markdown>{persona}</Markdown>
          )}
        </div>
      )}
    </div>
  );
}

function AnswerCard({ ex, onLibrary, onIngest }: { ex: Exchange; onLibrary: () => void; onIngest: () => void }) {
  const toast = useToast();
  const a = ex.answer!;
  const { shown, done } = useReveal(a.text); // hooks run unconditionally — before the not_found return
  const [detailsOpen, setDetailsOpen] = useState(false);
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
        {a.stripped && a.stripped.length > 0 && (
          <span title={`Removed as unsupported: ${a.stripped.join(", ")}`} style={badge("var(--warning)", "var(--warning-weak)")}>
            <Icon name="check" size={12} />
            {a.stripped.length} invented {a.stripped.length > 1 ? "numbers" : "number"} removed
          </span>
        )}
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-faint)" }}>{meta}</span>
      </div>
      <div style={{ position: "relative" }}>
        <Markdown>{shown}</Markdown>
        {!done && (
          <span style={{ display: "inline-block", width: 7, height: 15, marginLeft: 1, background: "var(--accent)", borderRadius: 1, verticalAlign: "text-bottom", opacity: 0.8, animation: "floaty 1s ease-in-out infinite" }} />
        )}
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
      {detailsOpen && a.model && (
        <div style={{ marginTop: 14, padding: "10px 12px", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 10, fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-muted)", display: "flex", flexWrap: "wrap", gap: "6px 16px", lineHeight: 1.5 }}>
          <span><b style={{ color: "var(--ink)" }}>model</b> {a.model}</span>
          <span><b style={{ color: "var(--ink)" }}>depth</b> {a.depth} → {a.fetch_n} candidates</span>
          <span><b style={{ color: "var(--ink)" }}>basket</b> {a.basket} → {a.basket_n} pages</span>
          <span><b style={{ color: "var(--ink)" }}>tokens</b> {a.input_tokens?.toLocaleString()} in · {a.output_tokens?.toLocaleString()} out</span>
          <span><b style={{ color: "var(--ink)" }}>cost</b> ~${(a.cost_usd ?? 0).toFixed(4)}</span>
          <span><b style={{ color: "var(--ink)" }}>latency</b> {((a.latency_ms ?? 0) / 1000).toFixed(1)}s</span>
        </div>
      )}
      <div style={{ display: "flex", gap: 6, marginTop: 16 }}>
        <button onClick={() => { navigator.clipboard?.writeText(a.text); toast("Answer copied", "copy"); }} style={actionBtnStyle}>
          <Icon name="copy" size={14} />
          Copy
        </button>
        {a.model && (
          <button onClick={() => setDetailsOpen((v) => !v)} style={actionBtnStyle}>
            <Icon name="observatory" size={14} />
            {detailsOpen ? "Hide" : "Details"}
          </button>
        )}
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
