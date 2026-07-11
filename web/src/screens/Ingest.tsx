import { useState } from "react";
import type { CSSProperties } from "react";
import { Icon } from "../icons";
import { PathChip, Seg } from "../components/PathChip";
import { useToast } from "../components/Toast";
import { INGEST_JOBS, INGEST_STEP_LABELS, REVIEW_ROWS, type IngestStepStatus } from "../data/mock";
import { actionBtnStyle, primaryBtnStyle, sectionLabelStyle, sepStyle } from "../ui";

const STEP_COLOR: Record<IngestStepStatus, string> = {
  done: "var(--success)",
  running: "var(--walk)",
  failed: "var(--danger)",
  pending: "var(--ink-faint)",
};
const STEP_BG: Record<IngestStepStatus, string> = {
  done: "var(--success-weak)",
  running: "var(--walk-weak)",
  failed: "var(--danger-weak)",
  pending: "var(--surface-sunk)",
};

function PipelineStepper({ states, dark }: { states: IngestStepStatus[]; dark: boolean }) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", padding: "0 4px" }}>
      {states.map((s, i) => (
        <div key={i} style={{ display: "contents" }}>
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: "none" }}>
            <span
              style={{
                flex: "none",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: 28,
                height: 28,
                borderRadius: "50%",
                background: STEP_BG[s],
                color: STEP_COLOR[s],
                border: `1.5px solid ${s === "pending" ? "var(--border)" : STEP_COLOR[s]}`,
                animation:
                  s === "running"
                    ? dark
                      ? "lampDark 1.4s ease-in-out infinite"
                      : "lamp 1.4s ease-in-out infinite"
                    : undefined,
              }}
            >
              {s === "done" ? (
                <Icon name="check" size={14} />
              ) : s === "failed" ? (
                <Icon name="x" size={13} />
              ) : (
                <Icon name="dot" size={s === "running" ? 12 : 8} />
              )}
            </span>
            <span
              style={{
                fontSize: 10.5,
                fontWeight: s === "running" || s === "failed" ? 700 : 500,
                color: s === "pending" ? "var(--ink-faint)" : STEP_COLOR[s],
                marginTop: 6,
                whiteSpace: "nowrap",
              }}
            >
              {INGEST_STEP_LABELS[i]}
            </span>
          </div>
          {i !== states.length - 1 && (
            <div
              style={{
                flex: 1,
                height: 2,
                margin: "13px 4px 0",
                background: s === "done" ? "var(--success)" : "var(--border)",
                minWidth: 14,
              }}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function ConfidenceBar({ value, gate }: { value: number; gate: number }) {
  const color = value >= gate ? "var(--success)" : "var(--warning)";
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, color: "var(--ink-muted)", marginBottom: 6 }}>
        <span>Confidence</span>
        <span style={{ fontFamily: "var(--mono)", fontWeight: 600, color }}>{value.toFixed(2)}</span>
      </div>
      <div style={{ position: "relative", height: 8, borderRadius: 5, background: "var(--surface-sunk)", border: "1px solid var(--border)" }}>
        <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${value * 100}%`, background: color, borderRadius: 5 }} />
        <div style={{ position: "absolute", left: `${gate * 100}%`, top: -4, bottom: -4, width: 2, background: "var(--ink)", borderRadius: 1 }} />
        <div
          style={{
            position: "absolute",
            left: `${gate * 100}%`,
            top: -20,
            transform: "translateX(-50%)",
            fontFamily: "var(--mono)",
            fontSize: 9.5,
            color: "var(--ink-muted)",
            whiteSpace: "nowrap",
          }}
        >
          gate {gate.toFixed(2)}
        </div>
      </div>
    </div>
  );
}

export function Ingest({ dark, goLibrary }: { dark: boolean; goLibrary: () => void }) {
  const toast = useToast();
  const [tab, setTab] = useState<"new" | "review">("new");
  const [reviewOpen, setReviewOpen] = useState<Record<string, boolean>>({});

  const tabStyle = (active: boolean): CSSProperties => ({
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    padding: "9px 16px",
    border: 0,
    borderRadius: 9,
    fontSize: 13.5,
    fontWeight: 600,
    cursor: "pointer",
    background: active ? "var(--surface-raised)" : "transparent",
    color: active ? "var(--ink)" : "var(--ink-muted)",
    boxShadow: active ? "var(--shadow-sm)" : "none",
  });

  return (
    <div style={{ height: "100%", overflowY: "auto" }}>
      <div style={{ maxWidth: 820, margin: "0 auto", padding: "28px 32px 40px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginBottom: 6 }}>
          <h1 style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 26, margin: 0, letterSpacing: -0.4 }}>Ingest</h1>
          <span style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 15, color: "var(--ink-muted)" }}>
            Add books to the library
          </span>
        </div>
        <p style={{ color: "var(--ink-muted)", fontSize: 14, margin: "0 0 20px" }}>
          Drop a document and the librarian parses, classifies, and shelves it — you approve where it lands.
        </p>

        <div style={{ display: "inline-flex", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 11, padding: 4, marginBottom: 22 }}>
          <button onClick={() => setTab("new")} style={tabStyle(tab === "new")}>
            New ingest
          </button>
          <button onClick={() => setTab("review")} style={tabStyle(tab === "review")}>
            Review queue{" "}
            <span
              style={{
                minWidth: 18,
                height: 18,
                padding: "0 5px",
                borderRadius: 9,
                background: "var(--warning)",
                color: "#fff",
                fontSize: 11,
                fontWeight: 700,
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              3
            </span>
          </button>
        </div>

        {tab === "new" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div style={{ border: "2px dashed var(--border-strong)", borderRadius: 14, background: "var(--surface-raised)", padding: 28, textAlign: "center" }}>
              <div
                style={{
                  display: "inline-flex",
                  width: 60,
                  height: 60,
                  borderRadius: 14,
                  background: "var(--accent-weak)",
                  color: "var(--accent)",
                  alignItems: "center",
                  justifyContent: "center",
                  marginBottom: 12,
                }}
              >
                <Icon name="inboxplus" size={30} sw={1.4} />
              </div>
              <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 17 }}>Drop a file to ingest</div>
              <div style={{ fontSize: 13, color: "var(--ink-muted)", margin: "5px 0 16px" }}>PDF, Markdown or HTML · or paste a URL</div>
              <div style={{ display: "flex", gap: 10, maxWidth: 480, margin: "0 auto" }}>
                <input
                  placeholder="https://…"
                  style={{
                    flex: 1,
                    height: 40,
                    padding: "0 13px",
                    border: "1px solid var(--border)",
                    borderRadius: 9,
                    background: "var(--surface-sunk)",
                    outline: "none",
                    fontSize: 13,
                    color: "var(--ink)",
                  }}
                />
                <button
                  onClick={() => toast("Fetch queued (mock)", "inboxplus")}
                  style={{ height: 40, padding: "0 18px", background: "var(--accent)", color: "var(--accent-ink)", border: 0, borderRadius: 9, fontSize: 13, fontWeight: 600, cursor: "pointer" }}
                >
                  Fetch
                </button>
              </div>
              <div style={{ fontSize: 11.5, fontStyle: "italic", color: "var(--ink-faint)", marginTop: 14 }}>
                Sources are classified automatically by the librarian
              </div>
            </div>

            <div style={{ ...sectionLabelStyle, marginTop: 6 }}>Active jobs</div>

            {INGEST_JOBS.map((j) => (
              <div key={j.id} style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: 14, padding: "18px 20px", boxShadow: "var(--shadow-sm)" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 11, marginBottom: 18 }}>
                  <span
                    style={{
                      flex: "none",
                      width: 34,
                      height: 34,
                      borderRadius: 9,
                      background: "var(--surface-sunk)",
                      color: "var(--page)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <Icon name="page" size={20} />
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600 }}>{j.file}</div>
                    <div style={{ fontSize: 11.5, color: "var(--ink-faint)", marginTop: 2 }}>{j.meta}</div>
                  </div>
                </div>
                <PipelineStepper states={j.steps} dark={dark} />

                {j.showRetry && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      marginTop: 16,
                      padding: "11px 14px",
                      background: "var(--danger-weak)",
                      border: "1px solid var(--border)",
                      borderLeft: "3px solid var(--danger)",
                      borderRadius: 10,
                    }}
                  >
                    <span style={{ color: "var(--danger)" }}>
                      <Icon name="alert" size={13} />
                    </span>
                    <span style={{ flex: 1, fontSize: 13, color: "var(--ink)" }}>Split failed — document has a corrupt page range.</span>
                    <button
                      onClick={() => toast("Retry queued", "return")}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        padding: "6px 12px",
                        background: "var(--danger)",
                        color: "#fff",
                        border: 0,
                        borderRadius: 8,
                        fontSize: 12.5,
                        fontWeight: 600,
                        cursor: "pointer",
                      }}
                    >
                      <Icon name="return" size={14} />
                      Retry
                    </button>
                  </div>
                )}

                {j.showClassify && (
                  <div style={{ marginTop: 18, paddingTop: 18, borderTop: "1px solid var(--border)" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: ".06em", textTransform: "uppercase", color: "var(--walk)" }}>
                        Classify · needs your OK
                      </span>
                    </div>
                    <div style={{ fontSize: 12, color: "var(--ink-muted)", marginBottom: 7 }}>Proposed placement — edit if wrong:</div>
                    <div
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 7,
                        padding: "8px 13px",
                        background: "var(--surface-sunk)",
                        border: "1px dashed var(--border-strong)",
                        borderRadius: 9,
                        fontSize: 12.5,
                        marginBottom: 16,
                      }}
                    >
                      <Seg s={{ kind: "domain", label: "AI", dot: true }} />
                      <span style={sepStyle}>▸</span>
                      <Seg s={{ kind: "shelf", label: "LLM", dot: true }} />
                      <span style={sepStyle}>▸</span>
                      <span style={{ color: "var(--book)", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: 4 }}>
                        + new shelf · Foundations
                      </span>
                    </div>
                    <ConfidenceBar value={0.86} gate={0.7} />
                    <div style={{ fontSize: 12.5, color: "var(--ink-muted)", lineHeight: 1.5, marginBottom: 16 }}>
                      Rationale — the document introduces the Transformer architecture and self-attention; strongest
                      overlap with LLM foundations, no existing shelf fits so a new one is proposed.
                    </div>
                    <div style={{ display: "flex", gap: 9 }}>
                      <button onClick={() => toast("Placement accepted — filing", "check")} style={primaryBtnStyle}>
                        <Icon name="check" size={15} />
                        Accept placement
                      </button>
                      <button onClick={() => toast("Location picker (mock)", "shelf")} style={{ ...actionBtnStyle, padding: "9px 15px" }}>
                        Change location
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}

            <div style={{ ...sectionLabelStyle, marginTop: 6 }}>Completed</div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 16,
                background: "var(--surface-raised)",
                border: "1px solid var(--border)",
                borderLeft: "3px solid var(--success)",
                borderRadius: 12,
                padding: "15px 18px",
                boxShadow: "var(--shadow-sm)",
                flexWrap: "wrap",
              }}
            >
              <span style={{ color: "var(--success)" }}>
                <Icon name="check" size={15} />
              </span>
              <PathChip
                small
                segs={[
                  { kind: "domain", label: "AI" },
                  { kind: "shelf", label: "LLM" },
                  { kind: "book", label: "Foundations" },
                ]}
              />
              <span style={{ flex: 1 }} />
              {["18 pages", "72 questions (vi+en)", "14.2k tokens", "31s"].map((m) => (
                <span key={m} style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-muted)" }}>
                  {m}
                </span>
              ))}
              <a
                href="#book"
                onClick={(e) => {
                  e.preventDefault();
                  goLibrary();
                }}
                style={{ fontSize: 12.5, fontWeight: 600 }}
              >
                Open book →
              </a>
            </div>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 16px", fontSize: 11, fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase", color: "var(--ink-faint)" }}>
              <span style={{ flex: 1 }}>Uncatalogued book</span>
              <span style={{ width: 110 }}>Proposed path</span>
              <span style={{ width: 90 }}>Confidence</span>
              <span style={{ width: 60 }}>Age</span>
              <span style={{ width: 20 }} />
            </div>
            {REVIEW_ROWS.map((r) => {
              const open = !!reviewOpen[r.id];
              const confColor = r.conf >= 0.7 ? "var(--success)" : "var(--warning)";
              return (
                <div key={r.id} style={{ background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: 12, boxShadow: "var(--shadow-sm)", overflow: "hidden" }}>
                  <div
                    onClick={() => setReviewOpen((s) => ({ ...s, [r.id]: !s[r.id] }))}
                    className="h-bg-hover"
                    style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 16px", cursor: "pointer" }}
                  >
                    <div style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ color: "var(--page)" }}>
                        <Icon name="page" size={20} />
                      </span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600 }}>{r.title}</span>
                    </div>
                    <div style={{ width: 110, fontSize: 11.5, color: "var(--ink-muted)", fontFamily: "var(--mono)" }}>
                      {r.path[0]} ▸ {r.path[1]}
                    </div>
                    <div style={{ width: 90 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--mono)", fontSize: 11, marginBottom: 3 }}>
                        <span style={{ color: "var(--warning)" }}>low</span>
                        <span style={{ fontWeight: 600, color: confColor }}>{r.conf.toFixed(2)}</span>
                      </div>
                      <div style={{ height: 5, borderRadius: 3, background: "var(--surface-sunk)", overflow: "hidden" }}>
                        <div style={{ height: "100%", width: `${r.conf * 100}%`, background: confColor, borderRadius: 3 }} />
                      </div>
                    </div>
                    <div style={{ width: 60, fontSize: 12, color: "var(--ink-faint)" }}>{r.age}</div>
                    <span style={{ width: 20, color: "var(--ink-faint)" }}>
                      <Icon name={open ? "chevDown" : "chevR"} size={13} />
                    </span>
                  </div>
                  {open && (
                    <div style={{ padding: "16px 18px", borderTop: "1px solid var(--border)", background: "var(--surface-sunk)", display: "flex", gap: 22, flexWrap: "wrap" }}>
                      <div style={{ flex: 1, minWidth: 200 }}>
                        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase", color: "var(--ink-faint)", marginBottom: 8 }}>
                          Preview · TOC excerpt
                        </div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
                          {r.toc.map((t) => (
                            <div key={t} style={{ fontSize: 12.5, color: "var(--ink-muted)" }}>
                              {t}
                            </div>
                          ))}
                        </div>
                      </div>
                      <div style={{ flex: 1, minWidth: 220 }}>
                        <div style={{ fontSize: 10.5, fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase", color: "var(--ink-faint)", marginBottom: 8 }}>
                          Place it
                        </div>
                        <PathChip
                          small
                          segs={[
                            { kind: "domain", label: r.path[0] },
                            { kind: "shelf", label: r.path[1] },
                            { kind: "book", label: r.path[2] },
                          ]}
                          style={{ background: "var(--surface-raised)", marginBottom: 12 }}
                        />
                        <div style={{ display: "flex", gap: 8 }}>
                          <button
                            onClick={() => {
                              setReviewOpen((s) => ({ ...s, [r.id]: false }));
                              toast("Approved — shelved", "check");
                            }}
                            style={{ ...primaryBtnStyle, padding: "8px 14px", fontSize: 12.5 }}
                          >
                            <Icon name="check" size={15} />
                            Approve shelf
                          </button>
                          <button onClick={() => toast("Re-classification queued", "return")} style={{ ...actionBtnStyle, padding: "8px 13px" }}>
                            Re-classify
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
