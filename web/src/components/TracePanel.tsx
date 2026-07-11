// The signature component — the librarian's walk, room by room.
import type { CSSProperties } from "react";
import { Icon } from "../icons";
import { KIND_META, iconBtnStyle, kindIconName } from "../ui";
import type { Trace, TraceStep } from "../data/mock";

interface TracePanelProps {
  trace: Trace | null;
  reveal: number;
  walking: boolean;
  dark: boolean;
  expanded: Record<number, boolean>;
  onToggleStep: (i: number) => void;
  onCollapse: () => void;
}

const counterColors = ["var(--walk)", "var(--page)", "var(--info)"];

function totalSteps(trace: Trace): number {
  return trace.mode === "linear"
    ? trace.steps.length
    : trace.branches.reduce((a, b) => a + b.steps.length, 0);
}

function LinearStep({
  st,
  index,
  isCurrent,
  showLine,
  dark,
  expanded,
  onToggle,
}: {
  st: TraceStep;
  index: number;
  isCurrent: boolean;
  showLine: boolean;
  dark: boolean;
  expanded: boolean;
  onToggle: (i: number) => void;
}) {
  const meta = KIND_META[st.kind];
  const back = st.status === "backtracked";
  const dotBg = back
    ? "var(--surface-sunk)"
    : isCurrent
      ? "var(--walk-weak)"
      : st.status === "read"
        ? "var(--surface-sunk)"
        : "var(--accent-weak)";
  const dotColor = back
    ? "var(--walk-reject)"
    : isCurrent
      ? "var(--walk)"
      : st.status === "read"
        ? "var(--page)"
        : "var(--accent)";
  const dotBorder = isCurrent ? "var(--walk)" : back ? "var(--border-strong)" : "transparent";
  const anim = isCurrent
    ? dark
      ? "lampDark 1.4s ease-in-out infinite"
      : "lamp 1.4s ease-in-out infinite"
    : undefined;

  const statusIcon = isCurrent ? null : st.status === "done" ? (
    <Icon name="check" size={12} />
  ) : back ? (
    <Icon name="return" size={12} />
  ) : (
    <Icon name="bmark" size={11} />
  );

  return (
    <div
      style={{
        display: "flex",
        gap: 11,
        animation: "stepIn .32s ease both",
        opacity: back && !expanded ? 0.62 : 1,
      }}
    >
      <div style={{ flex: "none", display: "flex", flexDirection: "column", alignItems: "center", width: 26 }}>
        <span
          style={{
            flex: "none",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 26,
            height: 26,
            borderRadius: 8,
            background: dotBg,
            color: dotColor,
            border: `1.5px solid ${dotBorder}`,
            animation: anim,
          }}
        >
          <Icon name={kindIconName(st.kind)} size={14} />
        </span>
        {showLine && (
          <span style={{ width: 2, flex: 1, minHeight: 18, background: "var(--border-strong)", margin: "2px 0" }} />
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0, paddingBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: ".05em",
              textTransform: "uppercase",
              color: meta.color,
            }}
          >
            {meta.label}
          </span>
          <span style={{ flex: 1 }} />
          <span
            style={
              isCurrent
                ? {
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: 10.5,
                    fontWeight: 700,
                    color: "var(--walk)",
                    textTransform: "uppercase",
                    letterSpacing: ".04em",
                  }
                : {
                    display: "inline-flex",
                    alignItems: "center",
                    color:
                      st.status === "done"
                        ? "var(--success)"
                        : back
                          ? "var(--walk-reject)"
                          : "var(--page)",
                  }
            }
          >
            {statusIcon}
            {isCurrent ? "walking" : st.status === "read" ? "read" : ""}
          </span>
        </div>
        <div
          style={{
            fontFamily: "var(--serif)",
            fontWeight: 600,
            fontSize: 13.5,
            lineHeight: 1.35,
            marginTop: 2,
            ...(back
              ? {
                  color: "var(--walk-reject)",
                  textDecoration: "line-through",
                  textDecorationThickness: 1,
                }
              : {}),
          }}
        >
          {st.title}
        </div>
        <div style={{ fontSize: 12.5, color: "var(--ink-muted)", marginTop: 2, lineHeight: 1.45 }}>{st.desc}</div>
        {st.snippet && (
          <div
            style={{
              marginTop: 8,
              padding: "9px 11px",
              background: "var(--surface-sunk)",
              border: "1px solid var(--border)",
              borderLeft: "2px solid var(--page)",
              borderRadius: 7,
              fontFamily: "var(--serif)",
              fontStyle: "italic",
              fontSize: 12.5,
              lineHeight: 1.5,
              color: "var(--ink-muted)",
            }}
          >
            {st.snippet}
          </div>
        )}
        {back && (
          <>
            <button
              onClick={() => onToggle(index)}
              style={{
                marginTop: 7,
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 11.5,
                color: "var(--walk-reject)",
                background: "none",
                border: 0,
                cursor: "pointer",
                fontFamily: "var(--sans)",
              }}
            >
              <Icon name={expanded ? "chevDown" : "chevR"} size={12} />
              {expanded ? "hide — why the librarian left" : "visited, not relevant — why?"}
            </button>
            {expanded && (
              <div
                style={{
                  marginTop: 6,
                  padding: "9px 11px",
                  background: "var(--surface-sunk)",
                  border: "1px solid var(--border)",
                  borderRadius: 7,
                  fontSize: 12,
                  lineHeight: 1.5,
                  color: "var(--ink-muted)",
                }}
              >
                {st.why}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export function TracePanel({ trace, reveal, walking, dark, expanded, onToggleStep, onCollapse }: TracePanelProps) {
  const branchTags = ["var(--domain)", "var(--shelf)", "var(--book)"];
  const total = trace ? totalSteps(trace) : 0;
  const terminalVisible = trace !== null && reveal >= total && total > 0;

  const terminalStyle: CSSProperties =
    trace?.terminal.kind === "found"
      ? {
          display: "flex",
          alignItems: "center",
          gap: 11,
          marginTop: 16,
          padding: "13px 15px",
          background: "var(--success-weak)",
          border: "1px solid var(--border)",
          borderLeft: "3px solid var(--success)",
          borderRadius: 11,
          color: "var(--success)",
          animation: "checkPop .4s ease both",
        }
      : {
          display: "flex",
          alignItems: "center",
          gap: 11,
          marginTop: 16,
          padding: "13px 15px",
          background: "var(--warning-weak)",
          border: "1px solid var(--border)",
          borderLeft: "3px solid var(--warning)",
          borderRadius: 11,
          color: "var(--warning)",
          animation: "fadeUp .3s ease both",
        };

  let seen = 0;

  return (
    <aside
      style={{
        flex: "none",
        width: 400,
        borderLeft: "1px solid var(--border)",
        background: "var(--surface-raised)",
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
      }}
    >
      <div
        style={{
          flex: "none",
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "16px 18px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <span style={{ color: "var(--walk)" }}>
          <Icon name="foot" size={18} />
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 14, lineHeight: 1.15 }}>
            The librarian's walk
          </div>
          <div style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 11.5, color: "var(--ink-muted)" }}>
            room by room
          </div>
        </div>
        <button onClick={onCollapse} title="Collapse panel" style={iconBtnStyle}>
          <Icon name="chevR" size={16} />
        </button>
      </div>

      {trace ? (
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "16px 18px 24px" }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
            {trace.counters.map((c, i) => (
              <div
                key={c.label}
                style={{
                  flex: 1,
                  background: "var(--surface-sunk)",
                  border: "1px solid var(--border)",
                  borderRadius: 9,
                  padding: "8px 10px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <span style={{ fontSize: 10.5, color: "var(--ink-faint)", letterSpacing: ".03em" }}>{c.label}</span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color: "var(--ink)" }}>
                    {c.value} / {c.max}
                  </span>
                </div>
                <div style={{ height: 4, borderRadius: 3, background: "var(--border)", marginTop: 6, overflow: "hidden" }}>
                  <div
                    style={{
                      height: "100%",
                      width: `${Math.round((c.value / c.max) * 100)}%`,
                      background: counterColors[i],
                      borderRadius: 3,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          {trace.mode === "linear" ? (
            <div style={{ position: "relative", paddingLeft: 6 }}>
              {trace.steps.slice(0, reveal).map((st, i) => (
                <LinearStep
                  key={i}
                  st={st}
                  index={i}
                  isCurrent={i === reveal - 1 && walking}
                  showLine={i < reveal - 1 || i < trace.steps.length - 1}
                  dark={dark}
                  expanded={!!expanded[i]}
                  onToggle={onToggleStep}
                />
              ))}
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {trace.branches.map((br, bi) => {
                const visible = br.steps.filter(() => {
                  seen += 1;
                  return seen <= reveal;
                });
                return (
                  <div
                    key={br.label}
                    style={{
                      border: "1px solid var(--border)",
                      borderRadius: 11,
                      background: "var(--surface-sunk)",
                      padding: "11px 12px",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 9 }}>
                      <span
                        style={{
                          fontSize: 10,
                          fontWeight: 700,
                          letterSpacing: ".04em",
                          textTransform: "uppercase",
                          color: branchTags[bi],
                          background: `color-mix(in srgb, ${branchTags[bi]} 14%, transparent)`,
                          padding: "2px 7px",
                          borderRadius: 5,
                        }}
                      >
                        Branch {bi + 1}
                      </span>
                      <span style={{ fontSize: 12.5, fontWeight: 600 }}>{br.label}</span>
                    </div>
                    <div style={{ paddingLeft: 4 }}>
                      {visible.map((st, si) => {
                        const meta = KIND_META[st.kind];
                        return (
                          <div
                            key={si}
                            style={{ display: "flex", alignItems: "center", gap: 9, padding: "3px 0", animation: "stepIn .3s ease both" }}
                          >
                            <span
                              style={{
                                flex: "none",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                width: 20,
                                height: 20,
                                borderRadius: 6,
                                background: "var(--surface-raised)",
                                color: meta.color,
                                border: "1px solid var(--border)",
                              }}
                            >
                              <Icon name={kindIconName(st.kind)} size={12} />
                            </span>
                            <span
                              style={{
                                fontSize: 9.5,
                                fontWeight: 700,
                                textTransform: "uppercase",
                                letterSpacing: ".04em",
                                color: meta.color,
                                minWidth: 52,
                              }}
                            >
                              {meta.label}
                            </span>
                            <span
                              style={{
                                fontSize: 12.5,
                                color: "var(--ink)",
                                whiteSpace: "nowrap",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                              }}
                            >
                              {st.title}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {terminalVisible && (
            <div style={terminalStyle}>
              <span style={{ color: trace.terminal.kind === "found" ? "var(--success)" : "var(--warning)" }}>
                <Icon name={trace.terminal.kind === "found" ? "check" : "alert"} size={trace.terminal.kind === "found" ? 22 : 20} sw={trace.terminal.kind === "found" ? 2.2 : 1.7} />
              </span>
              <div>
                <div style={{ fontWeight: 700, fontSize: 13.5, letterSpacing: ".02em" }}>
                  {trace.terminal.kind === "found" ? "FOUND" : "NOT FOUND"}
                </div>
                <div style={{ fontSize: 12, opacity: 0.85 }}>
                  {trace.terminal.kind === "found"
                    ? `${trace.terminal.pages} pages read · answer cited`
                    : "honest — nothing catalogued here yet"}
                </div>
              </div>
            </div>
          )}
        </div>
      ) : (
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            textAlign: "center",
            padding: 30,
            color: "var(--ink-faint)",
          }}
        >
          <span style={{ color: "var(--walk-reject)", marginBottom: 12 }}>
            <Icon name="foot" size={34} sw={1.4} />
          </span>
          <div style={{ fontSize: 13, lineHeight: 1.5, maxWidth: 200 }}>
            Ask a question — the librarian's route through the stacks appears here, room by room.
          </div>
        </div>
      )}
    </aside>
  );
}
