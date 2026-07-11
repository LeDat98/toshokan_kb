// The signature component — the librarian's walk, room by room, streamed live from the backend.
import type { CSSProperties } from "react";
import { Icon, type IconName } from "../icons";
import { iconBtnStyle } from "../ui";
import type { StepEvent } from "../api";

interface TracePanelProps {
  steps: StepEvent[];
  running: boolean;
  dark: boolean;
  expanded: Record<number, boolean>;
  onToggleStep: (i: number) => void;
  onCollapse: () => void;
  idle: boolean; // no walk started yet
}

const KIND_META: Record<string, { label: string; color: string; icon: IconName }> = {
  domain: { label: "Domain", color: "var(--domain)", icon: "domain" },
  shelf: { label: "Shelf", color: "var(--shelf)", icon: "shelf" },
  book: { label: "Book", color: "var(--book)", icon: "book" },
  page: { label: "Page", color: "var(--page)", icon: "page" },
};

const TERMINAL_ACTIONS = new Set(["found", "not_found", "budget"]);

function stepMeta(ev: StepEvent) {
  if (ev.action === "open") return KIND_META.book;
  if (ev.action === "read") return KIND_META.page;
  return KIND_META[ev.kind ?? "shelf"] ?? KIND_META.shelf;
}

export function TracePanel({
  steps,
  running,
  dark,
  expanded,
  onToggleStep,
  onCollapse,
  idle,
}: TracePanelProps) {
  const walkSteps = steps.filter((s) => !TERMINAL_ACTIONS.has(s.action));
  const terminal = steps.find((s) => TERMINAL_ACTIONS.has(s.action));
  const hops = steps.filter((s) => s.action === "enter" || s.action === "open").length;
  const pages = steps.filter((s) => s.action === "read").length;
  const counters: [string, number, number][] = [
    ["hops", hops, 12],
    ["pages", pages, 6],
    ["calls", 0, 2],
  ];
  const counterColors = ["var(--walk)", "var(--page)", "var(--info)"];

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

      {idle ? (
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
      ) : (
        <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "16px 18px 24px" }}>
          <div style={{ display: "flex", gap: 8, marginBottom: 18 }}>
            {counters.map((c, i) => (
              <div
                key={c[0]}
                style={{
                  flex: 1,
                  background: "var(--surface-sunk)",
                  border: "1px solid var(--border)",
                  borderRadius: 9,
                  padding: "8px 10px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                  <span style={{ fontSize: 10.5, color: "var(--ink-faint)", letterSpacing: ".03em" }}>{c[0]}</span>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 12, fontWeight: 600, color: "var(--ink)" }}>
                    {c[1]} / {c[2]}
                  </span>
                </div>
                <div style={{ height: 4, borderRadius: 3, background: "var(--border)", marginTop: 6, overflow: "hidden" }}>
                  <div
                    style={{
                      height: "100%",
                      width: `${Math.min(100, Math.round((c[1] / c[2]) * 100))}%`,
                      background: counterColors[i],
                      borderRadius: 3,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          <div style={{ position: "relative", paddingLeft: 6 }}>
            {walkSteps.map((ev, i) => (
              <Step
                key={i}
                ev={ev}
                isCurrent={running && i === walkSteps.length - 1 && !terminal}
                showLine={i < walkSteps.length - 1 || !terminal}
                dark={dark}
                expanded={!!expanded[i]}
                onToggle={() => onToggleStep(i)}
              />
            ))}
          </div>

          {terminal && <Terminal ev={terminal} />}
        </div>
      )}
    </aside>
  );
}

function Step({
  ev,
  isCurrent,
  showLine,
  dark,
  expanded,
  onToggle,
}: {
  ev: StepEvent;
  isCurrent: boolean;
  showLine: boolean;
  dark: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const meta = stepMeta(ev);
  const back = ev.status === "backtracked";
  const read = ev.action === "read";
  const dotBg = back ? "var(--surface-sunk)" : isCurrent ? "var(--walk-weak)" : read ? "var(--surface-sunk)" : "var(--accent-weak)";
  const dotColor = back ? "var(--walk-reject)" : isCurrent ? "var(--walk)" : read ? "var(--page)" : "var(--accent)";
  const dotBorder = isCurrent ? "var(--walk)" : back ? "var(--border-strong)" : "transparent";
  const anim = isCurrent ? (dark ? "lampDark 1.4s ease-in-out infinite" : "lamp 1.4s ease-in-out infinite") : undefined;

  return (
    <div style={{ display: "flex", gap: 11, animation: "stepIn .32s ease both", opacity: back && !expanded ? 0.62 : 1 }}>
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
          <Icon name={meta.icon} size={14} />
        </span>
        {showLine && <span style={{ width: 2, flex: 1, minHeight: 18, background: "var(--border-strong)", margin: "2px 0" }} />}
      </div>
      <div style={{ flex: 1, minWidth: 0, paddingBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: ".05em", textTransform: "uppercase", color: meta.color }}>
            {meta.label}
          </span>
          <span style={{ flex: 1 }} />
          <span
            style={
              isCurrent
                ? { display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10.5, fontWeight: 700, color: "var(--walk)", textTransform: "uppercase", letterSpacing: ".04em" }
                : { display: "inline-flex", alignItems: "center", color: back ? "var(--walk-reject)" : read ? "var(--page)" : "var(--success)" }
            }
          >
            {isCurrent ? null : ev.status === "done" ? <Icon name="check" size={12} /> : back ? <Icon name="return" size={12} /> : <Icon name="bmark" size={11} />}
            {isCurrent ? "walking" : read ? "read" : ""}
          </span>
        </div>
        <div
          style={{
            fontFamily: "var(--serif)",
            fontWeight: 600,
            fontSize: 13.5,
            lineHeight: 1.35,
            marginTop: 2,
            ...(back ? { color: "var(--walk-reject)", textDecoration: "line-through", textDecorationThickness: 1 } : {}),
          }}
        >
          {ev.title}
        </div>
        {read && ev.snippet && (
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
            {ev.snippet}
          </div>
        )}
        {!read && ev.detail && !back && (
          <div style={{ fontSize: 12.5, color: "var(--ink-muted)", marginTop: 2, lineHeight: 1.45 }}>{ev.detail}</div>
        )}
        {back && (
          <>
            <button
              onClick={onToggle}
              style={{ marginTop: 7, display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11.5, color: "var(--walk-reject)", background: "none", border: 0, cursor: "pointer", fontFamily: "var(--sans)" }}
            >
              <Icon name={expanded ? "chevDown" : "chevR"} size={12} />
              {expanded ? "hide — why the librarian left" : "visited, not relevant — why?"}
            </button>
            {expanded && ev.detail && (
              <div style={{ marginTop: 6, padding: "9px 11px", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 7, fontSize: 12, lineHeight: 1.5, color: "var(--ink-muted)" }}>
                {ev.detail}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function Terminal({ ev }: { ev: StepEvent }) {
  const found = ev.action === "found";
  const style: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 11,
    marginTop: 16,
    padding: "13px 15px",
    background: found ? "var(--success-weak)" : "var(--warning-weak)",
    border: "1px solid var(--border)",
    borderLeft: `3px solid ${found ? "var(--success)" : "var(--warning)"}`,
    borderRadius: 11,
    color: found ? "var(--success)" : "var(--warning)",
    animation: found ? "checkPop .4s ease both" : "fadeUp .3s ease both",
  };
  return (
    <div style={style}>
      <span style={{ color: found ? "var(--success)" : "var(--warning)" }}>
        <Icon name={found ? "check" : "alert"} size={found ? 22 : 20} sw={found ? 2.2 : 1.7} />
      </span>
      <div>
        <div style={{ fontWeight: 700, fontSize: 13.5, letterSpacing: ".02em" }}>{found ? "FOUND" : "NOT FOUND"}</div>
        <div style={{ fontSize: 12, opacity: 0.85 }}>
          {found ? "answer cited from the pages read" : "honest — nothing catalogued here yet"}
        </div>
      </div>
    </div>
  );
}
