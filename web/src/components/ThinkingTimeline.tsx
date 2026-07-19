// The librarian thinking out loud — a Chain-of-Thought timeline narrated from the REAL cascade events
// (docs/AGENT_ARCHITECTURE.md, Phase A). Every line is built from what actually happened this query —
// the candidate count, the pages picked, which escalation branch fired — so it reads differently for
// every question and is never a hardcoded script. Patterns (timeline, live-then-frozen timer,
// auto-collapse the instant the answer lands) are adapted from the NexusRAG study to our own idiom
// (inline styles + tokens + Icon set); no code copied. Honesty rule (P14): a line may only describe a
// decision the backend actually made.
import { useEffect, useRef, useState } from "react";
import { Icon, type IconName } from "../icons";
import type { StepEvent } from "../api";

type Tone = "scan" | "pick" | "widen" | "read" | "done" | "error" | "voice";

interface Thought {
  icon: IconName;
  text: string;
  tone: Tone;
}

const TONE_COLOR: Record<Tone, string> = {
  scan: "var(--accent)",
  pick: "var(--info)",
  widen: "var(--walk)",
  read: "var(--page)",
  done: "var(--success)",
  error: "var(--warning)",
  voice: "var(--accent)",
};
const TONE_WEAK: Record<Tone, string> = {
  scan: "var(--accent-weak)",
  pick: "var(--info-weak)",
  widen: "var(--walk-weak)",
  read: "var(--surface-sunk)",
  done: "var(--success-weak)",
  error: "var(--warning-weak)",
  voice: "var(--accent-weak)",
};

// A few phrasings per beat, picked by a stable seed so the SAME query varies run-to-run but never
// flickers within one render. The seed is real data (candidate count + pick count), so the choice
// itself is tied to what happened, not noise.
function pick<T>(arr: T[], seed: number): T {
  return arr[Math.abs(seed) % arr.length];
}

function buildThoughts(steps: StepEvent[], answered: boolean, notFound: boolean): Thought[] {
  const items: Thought[] = [];
  const lookupN = (() => {
    const l = steps.find((s) => s.action === "lookup");
    return l ? Number(/(\d+)/.exec(l.detail)?.[1] ?? 0) : 0;
  })();
  const pickCount = steps.filter((s) => s.action === "triage").length;
  const seed = lookupN + pickCount * 7;

  // Consecutive TRIAGE events are one decision (the librarian filling the basket), so buffer them and
  // flush as a single line — otherwise a 3-page pick reads as three separate thoughts.
  let triageBuf: StepEvent[] = [];
  const flush = () => {
    if (!triageBuf.length) return;
    const titles = triageBuf.slice(0, 3).map((t) => `"${t.title}"`).join(", ");
    const more = triageBuf.length > 3 ? ` +${triageBuf.length - 3} more` : "";
    items.push({
      icon: "bmark",
      tone: "pick",
      text: pick(
        [
          `Handing the shortlist to the librarian — ${triageBuf.length} are worth opening: ${titles}${more}.`,
          `The librarian keeps ${triageBuf.length}: ${titles}${more}.`,
          `Picked ${triageBuf.length} to open: ${titles}${more}.`,
        ],
        seed,
      ),
    });
    triageBuf = [];
  };

  // Walk the events in the order they actually happened, so the timeline mirrors the real process.
  for (const s of steps) {
    if (s.action === "triage") {
      triageBuf.push(s);
      continue;
    }
    flush();
    if (s.action === "lookup") {
      if (s.status === "notfound") {
        items.push({ icon: "search", tone: "error", text: "Combed the stacks — nothing here even looks close." });
      } else {
        items.push({
          icon: "search",
          tone: "scan",
          text: lookupN
            ? pick(
                [
                  `Asking the index for pages that might match… ${lookupN} came back.`,
                  `Scanning the stacks — ${lookupN} candidate pages look relevant.`,
                  `Ran down the shelves and set aside ${lookupN} pages that might fit.`,
                ],
                seed,
              )
            : "Scanning the stacks for anything relevant…",
        });
      }
    } else if (s.action === "read") {
      const n = Number(/(\d+)/.exec(s.detail)?.[1] ?? 0);
      items.push({
        icon: "book",
        tone: "read",
        text: n
          ? `Opening ${n} page${n > 1 ? "s" : ""} and reading the relevant sections.`
          : "Opening the chosen pages and reading the relevant sections.",
      });
    } else if (s.action === "compose") {
      items.push({
        icon: "toc",
        tone: "pick",
        text: pick(["Weighing what they say and drafting the answer…", "Reading through them and writing the answer…"], seed),
      });
    } else if (s.action === "expand") {
      const t = (s.title || "").toLowerCase();
      if (t.includes("full") && t.includes("same")) {
        items.push({ icon: "book", tone: "read", text: "Hmm — the sections alone read thin. Opening those pages in full." });
      } else if (t.includes("closest") || t.includes("reading")) {
        items.push({ icon: "book", tone: "read", text: "Before I give up, reading the closest pages in full to be sure." });
      } else {
        items.push({ icon: "return", tone: "widen", text: "Hmm — that's not enough. Asking the shelves for more candidates." });
      }
    } else if (s.action === "thought") {
      // The model's OWN first-person voice (D-061), piggybacked on the triage/answer call. Shown
      // verbatim, quoted, so it reads as the librarian thinking aloud rather than a system label.
      const said = (s.title || "").trim();
      if (said) items.push({ icon: "owl", tone: "voice", text: `"${said}"` });
    }
    // found / not_found are folded into the terminal line below.
  }
  flush();

  // Verify (P15: the whole answer is checked before it shows — this is the number/citation gate).
  if (answered) {
    items.push({ icon: "check", tone: "done", text: "Checked every figure against the sources — done." });
  }
  if (notFound) {
    items.push({ icon: "alert", tone: "error", text: "The library doesn't hold this yet — and I won't guess." });
  }
  return items;
}

function useElapsed(running: boolean): number {
  const start = useRef(Date.now());
  const [ms, setMs] = useState(0);
  useEffect(() => {
    if (!running) {
      setMs(Date.now() - start.current);
      return;
    }
    const id = window.setInterval(() => setMs(Date.now() - start.current), 100);
    return () => window.clearInterval(id);
  }, [running]);
  return ms;
}

function fmt(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  return `${m}m ${Math.round((ms % 60000) / 1000)}s`;
}

interface Props {
  steps: StepEvent[];
  running: boolean;
  answered: boolean;
  notFound: boolean;
  dark: boolean;
}

export function ThinkingTimeline({ steps, running, answered, notFound, dark }: Props) {
  const done = answered || notFound || !running;
  const [expanded, setExpanded] = useState(running);
  const collapsedOnce = useRef(false);
  const elapsed = useElapsed(running);

  // Auto-collapse the instant the query resolves — the single best trick from the study: show the
  // work, then get out of the answer's way. Re-expandable. Fires exactly once.
  useEffect(() => {
    if (done && !collapsedOnce.current) {
      collapsedOnce.current = true;
      setExpanded(false);
    }
  }, [done]);

  const thoughts = buildThoughts(steps, answered, notFound);
  const pages = steps.filter((s) => s.action === "triage").length;
  const summary = notFound
    ? "Searched the stacks — nothing catalogued yet"
    : `Walked the stacks${pages ? ` · read ${pages} page${pages > 1 ? "s" : ""}` : ""}`;

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="h-border-accent"
        style={{
          display: "flex", alignItems: "center", gap: 8, alignSelf: "flex-start",
          padding: "7px 12px", background: "var(--surface-raised)", border: "1px solid var(--border)",
          borderRadius: 20, cursor: "pointer", fontSize: 12.5, color: "var(--ink-muted)",
          fontFamily: "var(--serif)", fontStyle: "italic", boxShadow: "var(--shadow-sm)",
        }}
      >
        <span style={{ color: notFound ? "var(--warning)" : "var(--success)" }}>
          <Icon name={notFound ? "alert" : "check"} size={13} />
        </span>
        <span>{summary}</span>
        <span style={{ fontFamily: "var(--mono)", fontStyle: "normal", fontSize: 11, color: "var(--ink-faint)" }}>
          {fmt(elapsed)}
        </span>
        <Icon name="chevDown" size={12} />
      </button>
    );
  }

  return (
    <div
      style={{
        alignSelf: "stretch", background: "var(--surface-raised)", border: "1px solid var(--border)",
        borderRadius: 13, padding: "12px 14px", boxShadow: "var(--shadow-sm)",
        animation: "fadeUp .3s ease both",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={{ color: "var(--accent)" }}>
          <Icon name="owl" size={16} />
        </span>
        <span style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 13 }}>
          {running ? "Thinking" : "How I got there"}
        </span>
        {running && (
          <span style={{ display: "inline-flex", gap: 3 }}>
            {[0, 1, 2].map((i) => (
              <span key={i} style={{ width: 3, height: 3, borderRadius: 2, background: "var(--accent)", animation: `floaty 1s ease-in-out ${i * 0.15}s infinite` }} />
            ))}
          </span>
        )}
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)" }}>{fmt(elapsed)}</span>
        {done && (
          <button onClick={() => setExpanded(false)} title="Collapse" style={{ display: "flex", background: "none", border: 0, cursor: "pointer", color: "var(--ink-faint)", padding: 0 }}>
            <Icon name="chevR" size={14} />
          </button>
        )}
      </div>

      <div>
        {thoughts.map((th, i) => {
          const last = i === thoughts.length - 1;
          const active = running && last;
          const anim = active ? (dark ? "lampDark 1.4s ease-in-out infinite" : "lamp 1.4s ease-in-out infinite") : undefined;
          return (
            <div key={i} style={{ display: "flex", gap: 11, animation: "stepIn .3s ease both" }}>
              <div style={{ flex: "none", display: "flex", flexDirection: "column", alignItems: "center", width: 24 }}>
                <span
                  style={{
                    display: "flex", alignItems: "center", justifyContent: "center", width: 24, height: 24,
                    borderRadius: 7, background: TONE_WEAK[th.tone], color: TONE_COLOR[th.tone],
                    border: active ? `1.5px solid ${TONE_COLOR[th.tone]}` : "1.5px solid transparent",
                    animation: anim,
                  }}
                >
                  <Icon name={th.icon} size={13} />
                </span>
                {!last && <span style={{ width: 2, flex: 1, minHeight: 12, background: "var(--border-strong)", margin: "2px 0" }} />}
              </div>
              <div
                style={{
                  flex: 1, minWidth: 0, paddingBottom: last ? 0 : 12, fontSize: 13, lineHeight: 1.5,
                  fontFamily: "var(--serif)", color: active ? "var(--ink)" : "var(--ink-muted)",
                  fontStyle: th.tone === "error" ? "normal" : "italic",
                }}
              >
                {th.text}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
