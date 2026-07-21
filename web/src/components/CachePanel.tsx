import { useEffect, useState } from "react";
import { Icon } from "../icons";
import { useToast } from "./Toast";
import {
  fetchCache,
  toggleCache,
  editCacheEntry,
  deleteCacheEntry,
  type CacheEntry,
} from "../api";
import { chip, sectionLabelStyle } from "../ui";

function fmtDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

const iconBtn = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: 26,
  height: 26,
  border: 0,
  borderRadius: 7,
  background: "transparent",
  color: "var(--ink-faint)",
  cursor: "pointer",
} as const;

export function CachePanel() {
  const toast = useToast();
  const [enabled, setEnabled] = useState(true);
  const [entries, setEntries] = useState<CacheEntry[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [confirmDel, setConfirmDel] = useState<number | null>(null);

  const load = () =>
    fetchCache()
      .then((d) => {
        setEnabled(d.enabled);
        setEntries(d.entries);
        setLoaded(true);
      })
      .catch(() => setLoaded(true));

  useEffect(() => {
    load();
  }, []);

  const flip = () =>
    toggleCache(!enabled)
      .then((e) => {
        setEnabled(e);
        toast(e ? "Cache on" : "Cache off — every question runs fresh", "check");
      })
      .catch(() => toast("Couldn't toggle the cache", "alert"));

  const saveEdit = (id: number) => {
    const text = draft.trim();
    setEditing(null);
    if (!text) return;
    editCacheEntry(id, { answer: text })
      .then(() => {
        toast("Answer curated", "check");
        load();
      })
      .catch(() => toast("Save failed", "alert"));
  };

  const toggleEntry = (e: CacheEntry) =>
    editCacheEntry(e.id, { enabled: !e.enabled })
      .then(load)
      .catch(() => toast("Update failed", "alert"));

  const remove = (id: number) => {
    setConfirmDel(null);
    deleteCacheEntry(id)
      .then(load)
      .catch(() => toast("Delete failed", "alert"));
  };

  return (
    <div style={{ marginTop: 30 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <div style={sectionLabelStyle}>Cached answers</div>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 12, color: "var(--ink-muted)" }}>
          Semantically-repeated questions answered instantly, 0 tokens
        </span>
        <button
          onClick={flip}
          title={enabled ? "Turn the cache off" : "Turn the cache on"}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 7,
            height: 28,
            padding: "0 12px",
            borderRadius: 999,
            border: "1px solid var(--border)",
            cursor: "pointer",
            fontSize: 12,
            fontWeight: 600,
            background: enabled ? "var(--success-weak)" : "var(--surface-sunk)",
            color: enabled ? "var(--success)" : "var(--ink-muted)",
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: enabled ? "var(--success)" : "var(--ink-faint)",
            }}
          />
          {enabled ? "Cache on" : "Cache off"}
        </button>
      </div>

      <div
        style={{
          background: "var(--surface-raised)",
          border: "1px solid var(--border)",
          borderRadius: 13,
          boxShadow: "var(--shadow-sm)",
          overflow: "hidden",
        }}
      >
        {loaded && entries.length === 0 && (
          <div style={{ padding: "18px 16px", fontSize: 13, color: "var(--ink-muted)" }}>
            No cached answers yet. As readers ask, confident cited answers are remembered here — and
            you can edit any of them.
          </div>
        )}
        {entries.map((e) => (
          <div key={e.id} style={{ borderBottom: "1px solid var(--border)", opacity: e.enabled ? 1 : 0.55 }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 12, padding: "12px 15px" }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 13.5, fontWeight: 600 }}>{e.query}</span>
                  {e.curated && <span style={chip("var(--accent)", "var(--accent-weak)")}>curated</span>}
                </div>
                {editing === e.id ? (
                  <textarea
                    autoFocus
                    value={draft}
                    onChange={(ev) => setDraft(ev.target.value)}
                    onKeyDown={(ev) => {
                      if (ev.key === "Escape") setEditing(null);
                      if (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) saveEdit(e.id);
                    }}
                    rows={4}
                    style={{
                      width: "100%",
                      fontSize: 13,
                      lineHeight: 1.5,
                      padding: "8px 10px",
                      borderRadius: 8,
                      border: "1px solid var(--border-strong)",
                      background: "var(--surface)",
                      color: "var(--ink)",
                      outline: "none",
                      resize: "vertical",
                    }}
                  />
                ) : (
                  <div style={{ fontSize: 13, color: "var(--ink-muted)", lineHeight: 1.5, whiteSpace: "pre-wrap" }}>
                    {e.answer.length > 260 ? e.answer.slice(0, 260) + "…" : e.answer}
                  </div>
                )}
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6, fontSize: 11, color: "var(--ink-faint)", fontFamily: "var(--mono)" }}>
                  <span>{e.hits} hit{e.hits === 1 ? "" : "s"}</span>
                  <span>·</span>
                  <span>{e.confidence || "—"}</span>
                  <span>·</span>
                  <span>{fmtDate(e.created_at)}</span>
                </div>
                {editing === e.id && (
                  <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                    <button
                      onClick={() => saveEdit(e.id)}
                      style={{ padding: "5px 12px", background: "var(--accent)", color: "var(--accent-ink)", border: 0, borderRadius: 7, fontSize: 12, fontWeight: 600, cursor: "pointer" }}
                    >
                      Save (curate)
                    </button>
                    <button
                      onClick={() => setEditing(null)}
                      style={{ padding: "5px 12px", background: "var(--surface-sunk)", border: "1px solid var(--border)", borderRadius: 7, fontSize: 12, cursor: "pointer", color: "var(--ink-muted)" }}
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
              {editing !== e.id && (
                <div style={{ display: "flex", alignItems: "center", gap: 2, flex: "none" }}>
                  <button style={iconBtn} title={e.enabled ? "Disable" : "Enable"} onClick={() => toggleEntry(e)}>
                    <Icon name={e.enabled ? "check" : "dot"} size={15} />
                  </button>
                  <button
                    style={iconBtn}
                    title="Edit answer"
                    onClick={() => {
                      setEditing(e.id);
                      setDraft(e.answer);
                      setConfirmDel(null);
                    }}
                  >
                    <Icon name="pencil" size={14} />
                  </button>
                  {confirmDel === e.id ? (
                    <>
                      <button style={{ ...iconBtn, width: "auto", padding: "0 8px", color: "var(--danger)", fontSize: 11.5, fontWeight: 600 }} onClick={() => remove(e.id)}>
                        Delete
                      </button>
                      <button style={{ ...iconBtn, width: "auto", padding: "0 6px", fontSize: 11.5 }} onClick={() => setConfirmDel(null)}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button style={iconBtn} title="Delete" onClick={() => setConfirmDel(e.id)}>
                      <Icon name="x" size={14} />
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
