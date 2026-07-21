import { useEffect, useState } from "react";
import { Icon } from "../icons";
import { Sparkline } from "../components/Sparkline";
import { useToast } from "../components/Toast";
import { EVAL_DOMAINS, EVAL_RUNS, MISROUTES, type Outcome, type QueryType } from "../data/mock";
import { fetchObservatory, type ObservatoryData } from "../api";
import { CachePanel } from "../components/CachePanel";
import { KIND_META, actionBtnStyle, chip, kindIconName, sectionLabelStyle } from "../ui";

/** A small honest badge for panels not yet wired to a real backend feed (they need
 *  trajectory/analyzer.py, which is not built yet). It marks sample data as sample data. */
function PreviewTag() {
  return (
    <span
      title="Sample data — the trajectory analyzer isn't built yet"
      style={{
        ...chip("var(--ink-muted)", "var(--surface-sunk)"),
        fontSize: 9.5,
        letterSpacing: ".03em",
      }}
    >
      PREVIEW
    </span>
  );
}

const OUT_META: Record<Outcome, { c: string; cw: string }> = {
  FOUND: { c: "var(--success)", cw: "var(--success-weak)" },
  NOT_FOUND: { c: "var(--warning)", cw: "var(--warning-weak)" },
  AMBIGUOUS: { c: "var(--info)", cw: "var(--info-weak)" },
};
const TYPE_META: Record<QueryType, { c: string; cw: string }> = {
  Lookup: { c: "var(--accent)", cw: "var(--accent-weak)" },
  Synthesis: { c: "var(--info)", cw: "var(--info-weak)" },
  Explore: { c: "var(--ink-muted)", cw: "var(--surface-sunk)" },
};

type FixState = "open" | "approved" | "dismissed";

function EvalChart() {
  const mn = 82;
  const mx = 94;
  const IX = 4;
  const IY = 14;
  const mapX = (i: number) => IX + (i / (EVAL_RUNS.length - 1)) * (100 - 2 * IX);
  const mapY = (v: number) => IY + (1 - (v - mn) / (mx - mn)) * (100 - 2 * IY);
  const line = EVAL_RUNS.map((v, i) => `${mapX(i).toFixed(1)},${mapY(v).toFixed(1)}`).join(" ");
  return (
    <div style={{ position: "relative", height: 132, margin: "0 0 24px" }}>
      {[92, 88, 84].map((g) => (
        <div key={g}>
          <div style={{ position: "absolute", left: 0, right: 0, top: `${mapY(g).toFixed(1)}%`, borderTop: "1px dashed var(--border)" }} />
          <span
            style={{
              position: "absolute",
              left: 0,
              top: `${mapY(g).toFixed(1)}%`,
              transform: "translateY(-50%)",
              fontFamily: "var(--mono)",
              fontSize: 9.5,
              color: "var(--ink-faint)",
              background: "var(--surface-raised)",
              paddingRight: 5,
            }}
          >
            {g}%
          </span>
        </div>
      ))}
      <svg width="100%" height="100%" viewBox="0 0 100 100" preserveAspectRatio="none" style={{ position: "absolute", inset: 0, overflow: "visible", display: "block" }}>
        <defs>
          <linearGradient id="evalGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="var(--accent)" stopOpacity="0.16" />
            <stop offset="1" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={`${mapX(0).toFixed(1)},100 ${line} ${mapX(EVAL_RUNS.length - 1).toFixed(1)},100`} fill="url(#evalGrad)" stroke="none" />
        <polyline points={line} fill="none" stroke="var(--accent)" strokeWidth={2.25} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </svg>
      {EVAL_RUNS.map((v, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: `${mapX(i).toFixed(1)}%`,
            top: `${mapY(v).toFixed(1)}%`,
            transform: "translate(-50%,-50%)",
            width: 9,
            height: 9,
            borderRadius: "50%",
            background: "var(--surface-raised)",
            border: "2px solid var(--accent)",
            boxShadow: "var(--shadow-sm)",
          }}
        />
      ))}
      {EVAL_RUNS.map((_, i) => (
        <span
          key={`r${i}`}
          style={{
            position: "absolute",
            left: `${mapX(i).toFixed(1)}%`,
            bottom: -18,
            transform: "translateX(-50%)",
            fontFamily: "var(--mono)",
            fontSize: 9,
            color: "var(--ink-faint)",
          }}
        >
          r{i + 1}
        </span>
      ))}
    </div>
  );
}

export function Observatory() {
  const toast = useToast();
  const [expand, setExpand] = useState<Record<string, boolean>>({});
  const [fixes, setFixes] = useState<Record<string, FixState>>({});
  const [data, setData] = useState<ObservatoryData | null>(null);
  const [loadErr, setLoadErr] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchObservatory()
      .then((d) => alive && setData(d))
      .catch(() => alive && setLoadErr(true));
    return () => {
      alive = false;
    };
  }, []);

  const kpis = data?.available ? data.kpis : [];
  const trajectories = data?.trajectories ?? [];

  const fixState = (id: string): FixState => fixes[id] ?? "open";
  const fixCardStyle = (id: string) => ({
    background: "var(--surface-raised)",
    border: "1px solid var(--border)",
    borderRadius: 13,
    boxShadow: "var(--shadow-sm)",
    padding: "15px 16px",
    opacity: fixState(id) === "open" ? 1 : 0.55,
    pointerEvents: (fixState(id) === "open" ? "auto" : "none") as "auto" | "none",
  });
  const approve = (id: string) => {
    setFixes((f) => ({ ...f, [id]: "approved" }));
    toast("Fix applied · eval queued", "check");
  };
  const dismiss = (id: string) => setFixes((f) => ({ ...f, [id]: "dismissed" }));
  const fixBadge = (id: string) =>
    fixState(id) === "open" ? "" : fixState(id) === "approved" ? "Applied" : "Dismissed";

  const approveBtn = {
    flex: 1,
    padding: 8,
    background: "var(--accent)",
    color: "var(--accent-ink)",
    border: 0,
    borderRadius: 8,
    fontSize: 12.5,
    fontWeight: 600,
    cursor: "pointer",
  } as const;

  return (
    <div style={{ height: "100%", overflowY: "auto" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: "26px 32px 44px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginBottom: 4 }}>
          <h1 style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 26, margin: 0, letterSpacing: -0.4 }}>Observatory</h1>
          <span style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 15, color: "var(--ink-muted)" }}>
            Health & the learning loop
          </span>
        </div>
        <p style={{ color: "var(--ink-muted)", fontSize: 14, margin: "0 0 22px" }}>
          Watch how well the librarian routes — and approve the fixes that make the next walk shorter.
        </p>

        {kpis.length > 0 ? (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, marginBottom: 26 }}>
            {kpis.map((k) => (
              <div key={k.label} style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: 13, padding: "15px 16px", boxShadow: "var(--shadow-sm)" }}>
                <div style={{ fontSize: 11.5, color: "var(--ink-muted)", marginBottom: 8 }}>{k.label}</div>
                <div style={{ display: "flex", alignItems: "flex-end", gap: 8 }}>
                  <span style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 28, lineHeight: 1, letterSpacing: -0.5 }}>{k.value}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 10, minHeight: 20 }}>
                  <span style={{ fontSize: 11.5, fontWeight: 600, color: k.good ? "var(--success)" : "var(--danger)" }}>{k.delta}</span>
                  <span style={{ flex: 1 }} />
                  {k.spark.length > 1 && (
                    <Sparkline values={k.spark} width={60} height={20} color={k.good ? "var(--success)" : "var(--danger)"} />
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div
            style={{
              background: "var(--surface-raised)",
              border: "1px solid var(--border)",
              borderRadius: 13,
              padding: "18px 20px",
              boxShadow: "var(--shadow-sm)",
              marginBottom: 26,
              fontSize: 13,
              color: "var(--ink-muted)",
            }}
          >
            {loadErr
              ? "Couldn't reach the backend for live metrics."
              : data === null
                ? "Loading live metrics…"
                : "No traffic logged yet — ask a few questions on the Ask screen and they'll appear here."}
          </div>
        )}

        <div style={{ display: "grid", gridTemplateColumns: "1.55fr 1fr", gap: 20, alignItems: "start" }}>
          <div>
            <div style={{ ...sectionLabelStyle, marginBottom: 12 }}>Trajectories</div>
            <div style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: 13, boxShadow: "var(--shadow-sm)", overflow: "hidden" }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  padding: "9px 15px",
                  fontSize: 10.5,
                  fontWeight: 700,
                  letterSpacing: ".04em",
                  textTransform: "uppercase",
                  color: "var(--ink-faint)",
                  borderBottom: "1px solid var(--border)",
                }}
              >
                <span style={{ width: 38 }}>Time</span>
                <span style={{ flex: 1 }}>Query</span>
                <span style={{ width: 74 }}>Type</span>
                <span style={{ width: 44, textAlign: "right" }}>Hops</span>
                <span style={{ width: 36, textAlign: "right" }}>↩</span>
                <span style={{ width: 86 }}>Outcome</span>
                <span style={{ width: 40, textAlign: "right" }}>Dur</span>
              </div>
              {trajectories.length === 0 && (
                <div style={{ padding: "18px 15px", fontSize: 12.5, color: "var(--ink-muted)" }}>
                  {data === null && !loadErr
                    ? "Loading…"
                    : "No trajectories logged yet — every question you ask is recorded here."}
                </div>
              )}
              {trajectories.map((t) => (
                <div key={t.id} style={{ borderBottom: "1px solid var(--border)" }}>
                  <div
                    onClick={() => setExpand((e) => ({ ...e, [t.id]: !e[t.id] }))}
                    className="h-bg-hover"
                    style={{ display: "flex", alignItems: "center", gap: 10, padding: "11px 15px", cursor: "pointer", fontSize: 12.5 }}
                  >
                    <span style={{ width: 38, fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)" }}>{t.time}</span>
                    <span style={{ flex: 1, minWidth: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{t.query}</span>
                    <span style={{ width: 74 }}>
                      <span style={chip(TYPE_META[t.type].c, TYPE_META[t.type].cw)}>{t.type}</span>
                    </span>
                    <span style={{ width: 44, textAlign: "right", fontFamily: "var(--mono)", color: "var(--ink-muted)" }}>{t.hops}</span>
                    <span
                      style={{
                        width: 36,
                        textAlign: "right",
                        fontFamily: "var(--mono)",
                        fontSize: 12,
                        color: t.back > 0 ? "var(--walk)" : "var(--ink-faint)",
                        fontWeight: t.back > 0 ? 600 : 400,
                      }}
                    >
                      {t.back}
                    </span>
                    <span style={{ width: 86 }}>
                      <span style={chip(OUT_META[t.outcome].c, OUT_META[t.outcome].cw)}>{t.outcome}</span>
                    </span>
                    <span style={{ width: 40, textAlign: "right", fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-muted)" }}>{t.dur}</span>
                  </div>
                  {expand[t.id] && (
                    <div style={{ padding: "6px 15px 15px 53px", background: "var(--surface-sunk)" }}>
                      <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase", color: "var(--ink-faint)", margin: "8px 0 9px" }}>
                        Trace replay · read-only
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                        {t.replay.length === 0 && (
                          <span style={{ fontSize: 12, fontStyle: "italic", color: "var(--ink-faint)" }}>
                            No node-walk to replay — answered by {t.type.toLowerCase()}.
                          </span>
                        )}
                        {t.replay.map((rs, i) => (
                          <span key={i} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                            <span
                              style={{
                                flex: "none",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                width: 22,
                                height: 22,
                                borderRadius: 6,
                                background: "var(--surface-raised)",
                                color: rs.state === "back" ? "var(--walk-reject)" : KIND_META[rs.kind].color,
                                border: "1px solid var(--border)",
                              }}
                            >
                              <Icon name={kindIconName(rs.kind)} size={12} />
                            </span>
                            <span
                              style={{
                                fontSize: 12,
                                ...(rs.state === "back"
                                  ? { color: "var(--walk-reject)", textDecoration: "line-through" }
                                  : { color: "var(--ink)" }),
                              }}
                            >
                              {rs.title}
                            </span>
                            {i < t.replay.length - 1 && <span style={{ color: "var(--ink-faint)", fontSize: 11 }}>›</span>}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div style={{ ...sectionLabelStyle, margin: "24px 0 12px" }}>
              Eval runs <PreviewTag />
            </div>
            <div style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: 13, boxShadow: "var(--shadow-sm)", padding: "18px 20px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
                <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 15 }}>Routing accuracy over runs</div>
                <span style={{ flex: 1 }} />
                <button
                  onClick={() => toast("Eval run queued — costs tokens", "sparkle")}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 7,
                    padding: "8px 14px",
                    background: "var(--accent)",
                    color: "var(--accent-ink)",
                    border: 0,
                    borderRadius: 9,
                    fontSize: 12.5,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  <Icon name="sparkle" size={15} />
                  Run eval now
                </button>
              </div>
              <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)", marginBottom: 16 }}>~100 queries · costs tokens</div>
              <EvalChart />
              <div style={{ marginTop: 18, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
                <div style={{ fontSize: 12, color: "var(--ink-muted)", marginBottom: 12 }}>Last EvalReport · accuracy by domain</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {EVAL_DOMAINS.map((d) => (
                    <div key={d.n} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                      <span style={{ width: 100, fontSize: 12.5, fontFamily: "var(--serif)", fontWeight: 600 }}>{d.n}</span>
                      <div style={{ flex: 1, height: 8, borderRadius: 4, background: "var(--surface-sunk)", overflow: "hidden" }}>
                        <div style={{ height: 8, borderRadius: 4, background: "var(--accent)", width: `${d.v}%` }} />
                      </div>
                      <span style={{ width: 38, textAlign: "right", fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600 }}>{d.w}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
            <div>
              <div style={{ ...sectionLabelStyle, marginBottom: 12 }}>
                Where the librarian gets lost <PreviewTag />
              </div>
              <div style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: 13, boxShadow: "var(--shadow-sm)", overflow: "hidden" }}>
                {MISROUTES.map((m) => (
                  <div key={m.node} style={{ display: "flex", gap: 11, padding: "13px 15px", borderBottom: "1px solid var(--border)" }}>
                    <span
                      style={{
                        ...chip(
                          m.heat === "high" ? "var(--danger)" : m.heat === "med" ? "var(--warning)" : "var(--ink-muted)",
                          m.heat === "high" ? "var(--danger-weak)" : m.heat === "med" ? "var(--warning-weak)" : "var(--surface-sunk)",
                        ),
                        flex: "none",
                        alignSelf: "flex-start",
                      }}
                    >
                      {m.count}
                    </span>
                    <div>
                      <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 13.5 }}>{m.node}</div>
                      <div style={{ fontSize: 12, color: "var(--ink-muted)", lineHeight: 1.45, marginTop: 3 }}>{m.text}</div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div style={{ ...sectionLabelStyle, marginBottom: 12 }}>
                Suggested fixes <PreviewTag />
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div style={fixCardStyle("f1")}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 11 }}>
                    <span style={chip("var(--info)", "var(--info-weak)")}>Add see-also</span>
                    <span style={{ flex: 1 }} />
                    <span style={{ fontSize: 11, fontWeight: 700, color: "var(--success)" }}>{fixBadge("f1")}</span>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 9, fontSize: 12 }}>
                    <span style={{ color: "var(--shelf)", fontWeight: 600 }}>RAG ▸ Reranking</span>
                    <span style={{ color: "var(--ink-faint)" }}>→</span>
                    <span style={{ color: "var(--shelf)", fontWeight: 600 }}>ML ▸ Ranking</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", lineHeight: 1.45, margin: "9px 0 13px" }}>
                    7 backtracks would be avoided by linking these shelves.
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => approve("f1")} style={approveBtn}>
                      Approve
                    </button>
                    <button onClick={() => dismiss("f1")} style={{ ...actionBtnStyle, justifyContent: "center", flex: 1, padding: 8 }}>
                      Dismiss
                    </button>
                  </div>
                </div>

                <div style={fixCardStyle("f2")}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 11 }}>
                    <span style={chip("var(--ink-muted)", "var(--surface-sunk)")}>Rewrite description</span>
                    <span style={{ flex: 1 }} />
                    <span style={{ fontSize: 11, fontWeight: 700, color: "var(--success)" }}>{fixBadge("f2")}</span>
                  </div>
                  <div style={{ fontSize: 11.5, lineHeight: 1.5 }}>
                    <div style={{ color: "var(--danger)", textDecoration: "line-through", marginBottom: 5 }}>
                      “LLM — large language models.”
                    </div>
                    <div style={{ color: "var(--success)" }}>“LLM — model architectures & foundations; not retrieval scoring.”</div>
                  </div>
                  <div style={{ display: "flex", gap: 8, marginTop: 13 }}>
                    <button onClick={() => approve("f2")} style={approveBtn}>
                      Approve
                    </button>
                    <button onClick={() => dismiss("f2")} style={{ ...actionBtnStyle, justifyContent: "center", flex: 1, padding: 8 }}>
                      Dismiss
                    </button>
                  </div>
                </div>

                <div style={fixCardStyle("f3")}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 11 }}>
                    <span style={chip("var(--accent)", "var(--accent-weak)")}>Split shelf</span>
                    <span style={{ flex: 1 }} />
                    <span style={{ fontSize: 11, fontWeight: 700, color: "var(--success)" }}>{fixBadge("f3")}</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--ink-muted)", marginBottom: 9 }}>
                    Split <strong style={{ color: "var(--ink)" }}>ML</strong> (9 books) into:
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 5, fontSize: 12 }}>
                    {[
                      ["Classical", "5"],
                      ["Ensembles", "3"],
                      ["Probabilistic", "1"],
                    ].map(([name, n]) => (
                      <div key={name} style={{ display: "flex", justifyContent: "space-between" }}>
                        <span>{name}</span>
                        <span style={{ fontFamily: "var(--mono)", color: "var(--ink-faint)" }}>{n}</span>
                      </div>
                    ))}
                  </div>
                  <div style={{ fontSize: 11, fontStyle: "italic", color: "var(--warning)", margin: "11px 0 13px" }}>
                    ⚑ eval-gated — applies only if routing accuracy holds
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button onClick={() => approve("f3")} style={approveBtn}>
                      Approve
                    </button>
                    <button onClick={() => dismiss("f3")} style={{ ...actionBtnStyle, justifyContent: "center", flex: 1, padding: 8 }}>
                      Dismiss
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <CachePanel />
      </div>
    </div>
  );
}
