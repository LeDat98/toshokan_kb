import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Icon } from "../icons";
import { PathChip } from "../components/PathChip";
import { useToast } from "../components/Toast";
import {
  approveReview,
  fetchReview,
  streamImport,
  streamIngest,
  type ImportReport,
  type IngestOutcome,
  type IngestStep,
  type ReviewRow,
} from "../api";
import { actionBtnStyle, badge, primaryBtnStyle, sectionLabelStyle } from "../ui";

const STAGES = ["parse", "split", "classify", "file"] as const;
const STAGE_LABEL: Record<string, string> = {
  parse: "Parse",
  split: "Split",
  classify: "Classify",
  file: "File",
};

function pathToSegs(path: string) {
  const kinds = ["domain", "shelf", "book", "page"] as const;
  return path.split(" ▸ ").filter(Boolean).map((label, i) => ({
    kind: kinds[Math.min(i, kinds.length - 1)],
    label,
    dot: true,
  }));
}

export function Ingest({ dark, goLibrary }: { dark: boolean; goLibrary: () => void }) {
  const [tab, setTab] = useState<"new" | "review">("new");
  const [reviewCount, setReviewCount] = useState(0);

  const refreshReview = () => fetchReview().then((r) => setReviewCount(r.length)).catch(() => {});
  useEffect(() => {
    refreshReview();
  }, []);

  return (
    <div style={{ height: "100%", overflowY: "auto" }}>
      <div style={{ maxWidth: 820, margin: "0 auto", padding: "28px 32px 40px" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginBottom: 6 }}>
          <h1 style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 26, margin: 0, letterSpacing: -0.4 }}>Ingest</h1>
          <span style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 15, color: "var(--ink-muted)" }}>Add knowledge to the library</span>
        </div>
        <p style={{ color: "var(--ink-muted)", fontSize: 14, margin: "0 0 20px" }}>
          Import a structured folder, or drop a single document — the librarian parses it, decides where it belongs, and files it (or asks you when unsure).
        </p>

        <div style={{ display: "inline-flex", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 11, padding: 4, marginBottom: 22 }}>
          <TabButton active={tab === "new"} onClick={() => setTab("new")}>New ingest</TabButton>
          <TabButton active={tab === "review"} onClick={() => { setTab("review"); refreshReview(); }}>
            Review queue
            {reviewCount > 0 && (
              <span style={{ minWidth: 18, height: 18, padding: "0 5px", borderRadius: 9, background: "var(--warning)", color: "#fff", fontSize: 11, fontWeight: 700, display: "inline-flex", alignItems: "center", justifyContent: "center" }}>{reviewCount}</span>
            )}
          </TabButton>
        </div>

        {tab === "new" ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 22 }}>
            <DocumentIngest dark={dark} goLibrary={goLibrary} onChanged={refreshReview} />
            <FolderImport onChanged={refreshReview} />
          </div>
        ) : (
          <ReviewQueue onChanged={() => { refreshReview(); }} goLibrary={goLibrary} />
        )}
      </div>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "9px 16px", border: 0, borderRadius: 9, fontSize: 13.5, fontWeight: 600, cursor: "pointer", background: active ? "var(--surface-raised)" : "transparent", color: active ? "var(--ink)" : "var(--ink-muted)", boxShadow: active ? "var(--shadow-sm)" : "none" }}>
      {children}
    </button>
  );
}

const cardStyle: CSSProperties = { background: "var(--surface-raised)", border: "1px solid var(--border)", borderRadius: 14, padding: "20px 22px", boxShadow: "var(--shadow-sm)" };
const inputStyle: CSSProperties = { flex: 1, height: 40, padding: "0 13px", border: "1px solid var(--border)", borderRadius: 9, background: "var(--surface-sunk)", outline: "none", fontSize: 13, color: "var(--ink)" };

// ---------------------------------------------------------------- document ingest

function DocumentIngest({ dark, goLibrary, onChanged }: { dark: boolean; goLibrary: () => void; onChanged: () => void }) {
  const toast = useToast();
  const [url, setUrl] = useState("");
  const [fileName, setFileName] = useState("");
  const [steps, setSteps] = useState<IngestStep[]>([]);
  const [outcome, setOutcome] = useState<IngestOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const run = () => {
    const file = fileRef.current?.files?.[0];
    if (!file && !url.trim()) {
      toast("Choose a file or paste a URL", "alert");
      return;
    }
    const form = new FormData();
    if (file) form.append("file", file);
    else form.append("url", url.trim());
    setSteps([]);
    setOutcome(null);
    setBusy(true);
    streamIngest(form, {
      onStep: (s) => setSteps((prev) => [...prev.filter((p) => p.stage !== s.stage), s]),
      onOutcome: (o) => setOutcome(o),
      onError: (m) => toast(m, "alert"),
      onDone: () => {
        setBusy(false);
        onChanged();
      },
    });
  };

  const statusOf = (stage: string): IngestStep["status"] | "pending" =>
    steps.find((s) => s.stage === stage)?.status ?? "pending";

  return (
    <div>
      <div style={{ ...sectionLabelStyle, marginBottom: 10 }}>Ingest one document</div>
      <div style={cardStyle}>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <input ref={fileRef} type="file" accept=".pdf,.md,.markdown,.txt,.html,.htm" onChange={(e) => setFileName(e.target.files?.[0]?.name ?? "")} style={{ display: "none" }} />
          <button onClick={() => fileRef.current?.click()} style={{ ...actionBtnStyle, height: 40, padding: "0 14px" }}>
            <Icon name="inboxplus" size={16} />
            {fileName || "Choose file (pdf/md/html)"}
          </button>
          <span style={{ color: "var(--ink-faint)", fontSize: 12 }}>or</span>
          <input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://… (a page URL)" style={inputStyle} />
          <button onClick={run} disabled={busy} style={{ ...primaryBtnStyle, height: 40, opacity: busy ? 0.6 : 1 }}>
            {busy ? "Ingesting…" : "Ingest"}
          </button>
        </div>
        <div style={{ fontSize: 11.5, fontStyle: "italic", color: "var(--ink-faint)", marginTop: 10 }}>
          The librarian classifies it into the tree; low-confidence placements go to the review queue.
        </div>

        {steps.length > 0 && (
          <div style={{ marginTop: 18, paddingTop: 16, borderTop: "1px solid var(--border)" }}>
            <Stepper stages={STAGES as unknown as string[]} statusOf={statusOf} dark={dark} steps={steps} />
          </div>
        )}

        {outcome && (
          <div style={{ marginTop: 18, padding: "14px 16px", borderRadius: 11, border: "1px solid var(--border)", borderLeft: `3px solid ${outcome.gated ? "var(--warning)" : "var(--success)"}`, background: outcome.gated ? "var(--warning-weak)" : "var(--success-weak)" }}>
            {outcome.gated ? (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <span style={{ color: "var(--warning)" }}><Icon name="alert" size={15} /></span>
                  <strong style={{ fontSize: 13.5 }}>Sent to review</strong>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-muted)" }}>confidence {outcome.confidence.toFixed(2)}</span>
                </div>
                <div style={{ fontSize: 13, color: "var(--ink-muted)", marginBottom: 8 }}>Proposed: {outcome.proposed_path} — {outcome.rationale}</div>
              </>
            ) : (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <span style={{ color: "var(--success)" }}><Icon name="check" size={15} /></span>
                  <strong style={{ fontSize: 13.5 }}>Filed</strong>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-muted)" }}>{outcome.n_pages} pages · confidence {outcome.confidence.toFixed(2)}</span>
                </div>
                <PathChip small segs={pathToSegs(outcome.book_path)} onClick={goLibrary} hover title="Open in the library" />
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Stepper({ stages, statusOf, dark, steps }: { stages: string[]; statusOf: (s: string) => string; dark: boolean; steps: IngestStep[] }) {
  const color = { done: "var(--success)", gated: "var(--warning)", running: "var(--walk)", failed: "var(--danger)", pending: "var(--ink-faint)" } as Record<string, string>;
  const bg = { done: "var(--success-weak)", gated: "var(--warning-weak)", running: "var(--walk-weak)", failed: "var(--danger-weak)", pending: "var(--surface-sunk)" } as Record<string, string>;
  return (
    <div style={{ display: "flex", alignItems: "flex-start", padding: "0 4px" }}>
      {stages.map((stage, i) => {
        const st = statusOf(stage);
        const detail = steps.find((s) => s.stage === stage)?.detail ?? "";
        return (
          <div key={stage} style={{ display: "contents" }}>
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", flex: "none", minWidth: 84 }}>
              <span style={{ width: 28, height: 28, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", background: bg[st], color: color[st], border: `1.5px solid ${st === "pending" ? "var(--border)" : color[st]}`, animation: st === "running" ? (dark ? "lampDark 1.4s ease-in-out infinite" : "lamp 1.4s ease-in-out infinite") : undefined }}>
                {st === "done" ? <Icon name="check" size={14} /> : st === "gated" ? <Icon name="alert" size={13} /> : st === "failed" ? <Icon name="x" size={13} /> : <Icon name="dot" size={st === "running" ? 12 : 8} />}
              </span>
              <span style={{ fontSize: 10.5, fontWeight: st === "running" || st === "gated" ? 700 : 500, color: st === "pending" ? "var(--ink-faint)" : color[st], marginTop: 6 }}>{STAGE_LABEL[stage]}</span>
              {detail && <span style={{ fontSize: 9.5, color: "var(--ink-faint)", marginTop: 2, maxWidth: 80, textAlign: "center", lineHeight: 1.3 }}>{detail.slice(0, 28)}</span>}
            </div>
            {i < stages.length - 1 && <div style={{ flex: 1, height: 2, margin: "13px 2px 0", background: statusOf(stages[i]) === "done" ? "var(--success)" : "var(--border)", minWidth: 12 }} />}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- folder import

function FolderImport({ onChanged }: { onChanged: () => void }) {
  const toast = useToast();
  const [path, setPath] = useState("");
  const [domain, setDomain] = useState("");
  const [shelves, setShelves] = useState("auto");
  const [logs, setLogs] = useState<string[]>([]);
  const [report, setReport] = useState<ImportReport | null>(null);
  const [busy, setBusy] = useState(false);

  const run = () => {
    if (!path.trim() || !domain.trim()) {
      toast("Enter a folder path and a domain", "alert");
      return;
    }
    setLogs([]);
    setReport(null);
    setBusy(true);
    streamImport(
      { folder_path: path.trim(), domain: domain.trim(), shelves },
      {
        onLog: (m) => setLogs((prev) => [...prev, m]),
        onReport: (r) => setReport(r),
        onError: (m) => toast(m, "alert"),
        onDone: () => {
          setBusy(false);
          onChanged();
        },
      },
    );
  };

  return (
    <div>
      <div style={{ ...sectionLabelStyle, marginBottom: 10 }}>Import a structured folder</div>
      <div style={cardStyle}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="Folder path on this machine, e.g. C:\corpora\retail\knowledge" style={inputStyle} />
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <input value={domain} onChange={(e) => setDomain(e.target.value)} placeholder="Domain (e.g. Retail)" style={{ ...inputStyle, maxWidth: 220 }} />
            <select value={shelves} onChange={(e) => setShelves(e.target.value)} style={{ ...inputStyle, maxWidth: 260, cursor: "pointer" }}>
              <option value="auto">Shelves: auto (AI groups by theme)</option>
              <option value="single">Shelves: single</option>
              <option value="priority">Shelves: by P0/P1/P2 priority</option>
            </select>
            <button onClick={run} disabled={busy} style={{ ...primaryBtnStyle, height: 40, opacity: busy ? 0.6 : 1 }}>
              {busy ? "Importing…" : "Import"}
            </button>
          </div>
        </div>
        <div style={{ fontSize: 11.5, fontStyle: "italic", color: "var(--ink-faint)", marginTop: 10 }}>
          Sub-folders become books, files become pages; the folder structure is preserved.
        </div>

        {logs.length > 0 && !report && (
          <div style={{ marginTop: 14, padding: "10px 12px", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 9, fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-muted)", maxHeight: 160, overflowY: "auto" }}>
            {logs.slice(-8).map((l, i) => <div key={i}>{l}</div>)}
          </div>
        )}

        {report && (
          <div style={{ marginTop: 16, padding: "14px 16px", borderRadius: 11, border: "1px solid var(--border)", borderLeft: "3px solid var(--success)", background: "var(--success-weak)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
              <span style={{ color: "var(--success)" }}><Icon name="check" size={15} /></span>
              <strong style={{ fontSize: 13.5 }}>Imported into {report.domain}</strong>
              <span style={{ fontFamily: "var(--mono)", fontSize: 11.5, color: "var(--ink-muted)" }}>{report.shelves} shelves · {report.books} books · {report.pages} pages{report.skipped_pages ? ` · ${report.skipped_pages} skipped` : ""}</span>
            </div>
            <div style={{ fontSize: 12, color: "var(--ink-muted)" }}>
              provided by source: <span style={{ fontFamily: "var(--mono)" }}>{report.provided.join(", ")}</span> · filled by import: <span style={{ fontFamily: "var(--mono)" }}>{report.missing.join(", ") || "nothing"}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- review queue

function ReviewQueue({ onChanged, goLibrary }: { onChanged: () => void; goLibrary: () => void }) {
  const toast = useToast();
  const [rows, setRows] = useState<ReviewRow[] | null>(null);
  const [edits, setEdits] = useState<Record<string, { domain: string; shelf: string }>>({});

  const load = () => fetchReview().then(setRows).catch(() => setRows([]));
  useEffect(() => {
    load();
  }, []);

  const approve = async (r: ReviewRow) => {
    const e = edits[r.id] ?? { domain: r.proposed_domain, shelf: r.proposed_shelf };
    if (!e.domain.trim() || !e.shelf.trim()) {
      toast("Enter a domain and shelf", "alert");
      return;
    }
    try {
      const path = await approveReview(r.id, e.domain.trim(), e.shelf.trim());
      toast(`Filed under ${path}`, "check");
      load();
      onChanged();
    } catch {
      toast("Approve failed", "alert");
    }
  };

  if (rows === null) return <div style={{ color: "var(--ink-faint)", fontSize: 13 }}>Loading…</div>;
  if (rows.length === 0)
    return (
      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", padding: "50px 20px", color: "var(--ink-faint)" }}>
        <span style={{ color: "var(--border-strong)", marginBottom: 12 }}><Icon name="check" size={30} /></span>
        <div style={{ fontFamily: "var(--serif)", fontSize: 16, color: "var(--ink-muted)" }}>Nothing to review</div>
        <div style={{ fontFamily: "var(--serif)", fontStyle: "italic", fontSize: 13 }}>Confident ingests file themselves; unsure ones land here.</div>
      </div>
    );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {rows.map((r) => {
        const e = edits[r.id] ?? { domain: r.proposed_domain, shelf: r.proposed_shelf };
        return (
          <div key={r.id} style={cardStyle}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <span style={{ color: "var(--page)" }}><Icon name="page" size={20} /></span>
              <span style={{ fontFamily: "var(--mono)", fontSize: 13, fontWeight: 600 }}>{r.title}</span>
              <span style={{ fontSize: 11.5, color: "var(--ink-faint)" }}>{r.n_pages} pages</span>
              <span style={{ flex: 1 }} />
              {r.confidence != null && <span style={badge("var(--warning)", "var(--warning-weak)")}>confidence {r.confidence.toFixed(2)}</span>}
            </div>
            <div style={{ fontSize: 12.5, color: "var(--ink-muted)", marginBottom: 12 }}>
              Proposed <strong style={{ color: "var(--ink)" }}>{r.proposed_domain} ▸ {r.proposed_shelf}</strong>{r.rationale ? ` — ${r.rationale}` : ""}
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              <input value={e.domain} onChange={(ev) => setEdits((p) => ({ ...p, [r.id]: { ...e, domain: ev.target.value } }))} placeholder="Domain" style={{ ...inputStyle, height: 36, maxWidth: 180 }} />
              <span style={{ color: "var(--ink-faint)" }}>▸</span>
              <input value={e.shelf} onChange={(ev) => setEdits((p) => ({ ...p, [r.id]: { ...e, shelf: ev.target.value } }))} placeholder="Shelf" style={{ ...inputStyle, height: 36, maxWidth: 180 }} />
              <button onClick={() => approve(r)} style={{ ...primaryBtnStyle, height: 36, padding: "0 14px", fontSize: 12.5 }}>
                <Icon name="check" size={14} />
                Approve
              </button>
            </div>
          </div>
        );
      })}
      <button onClick={goLibrary} style={{ ...actionBtnStyle, alignSelf: "flex-start" }}>Open the library →</button>
    </div>
  );
}
