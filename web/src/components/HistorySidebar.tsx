import { useState } from "react";
import { Icon } from "../icons";
import type { ConversationMeta } from "../api";

interface Props {
  conversations: ConversationMeta[];
  activeId: string | null;
  maxPinned: number;
  collapsed: boolean;
  onToggleCollapse: () => void;
  onNew: () => void;
  onOpen: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
  onPin: (id: string, pinned: boolean) => void;
}

/** A specific creation date + time, in the viewer's locale — "Jul 20, 2026, 02:02 PM". */
function fmtDate(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const labelStyle = {
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: ".06em",
  textTransform: "uppercase" as const,
  color: "var(--ink-faint)",
  padding: "0 4px",
  margin: "2px 0 6px",
};

const iconBtn = {
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  width: 22,
  height: 22,
  border: 0,
  borderRadius: 6,
  background: "transparent",
  color: "var(--ink-faint)",
  cursor: "pointer",
} as const;

export function HistorySidebar({
  conversations,
  activeId,
  maxPinned,
  collapsed,
  onToggleCollapse,
  onNew,
  onOpen,
  onRename,
  onDelete,
  onPin,
}: Props) {
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [confirmDel, setConfirmDel] = useState<string | null>(null);

  const startEdit = (c: ConversationMeta) => {
    setEditing(c.id);
    setDraft(c.title);
    setConfirmDel(null);
  };
  const commitEdit = () => {
    if (editing) {
      const t = draft.trim();
      if (t) onRename(editing, t);
    }
    setEditing(null);
  };

  if (collapsed) {
    return (
      <button
        onClick={onToggleCollapse}
        title="Show conversations"
        style={{
          flex: "none",
          width: 40,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 10,
          padding: "14px 0",
          background: "var(--surface-sunk)",
          border: 0,
          borderRight: "1px solid var(--border)",
          cursor: "pointer",
          color: "var(--ink-muted)",
        }}
      >
        <Icon name="chevR" size={16} />
        <Icon name="ask" size={16} />
      </button>
    );
  }

  const pinned = conversations.filter((c) => c.pinned);
  const rest = conversations.filter((c) => !c.pinned);

  const row = (c: ConversationMeta) => {
    const active = c.id === activeId;
    const isEditing = editing === c.id;
    const isConfirm = confirmDel === c.id;
    return (
      <div
        key={c.id}
        className="h-bg-hover"
        onClick={() => !isEditing && !isConfirm && onOpen(c.id)}
        style={{
          position: "relative",
          padding: "8px 9px",
          borderRadius: 9,
          cursor: isEditing ? "default" : "pointer",
          background: active ? "var(--accent-weak)" : "transparent",
          border: active ? "1px solid var(--border-strong)" : "1px solid transparent",
          marginBottom: 3,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {c.pinned && (
            <span style={{ flex: "none", color: "var(--accent)", display: "flex" }}>
              <Icon name="bmark" size={12} />
            </span>
          )}
          {isEditing ? (
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onClick={(e) => e.stopPropagation()}
              onBlur={commitEdit}
              onKeyDown={(e) => {
                if (e.key === "Enter") commitEdit();
                if (e.key === "Escape") setEditing(null);
              }}
              style={{
                flex: 1,
                minWidth: 0,
                fontSize: 12.5,
                padding: "2px 5px",
                border: "1px solid var(--border-strong)",
                borderRadius: 5,
                background: "var(--surface)",
                color: "var(--ink)",
                outline: "none",
              }}
            />
          ) : (
            <span
              onDoubleClick={(e) => {
                e.stopPropagation();
                startEdit(c);
              }}
              title={c.title}
              style={{
                flex: 1,
                minWidth: 0,
                fontSize: 12.5,
                fontWeight: active ? 600 : 500,
                color: "var(--ink)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {c.title || "Untitled"}
            </span>
          )}
        </div>

        {!isEditing && !isConfirm && (
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 3, paddingLeft: c.pinned ? 18 : 0 }}>
            <span style={{ fontSize: 10.5, fontFamily: "var(--mono)", color: "var(--ink-faint)" }}>
              {fmtDate(c.created_at)}
            </span>
            <span style={{ flex: 1 }} />
            <span className="h-row-actions" style={{ display: "flex", gap: 2 }}>
              <button
                style={{ ...iconBtn, color: c.pinned ? "var(--accent)" : "var(--ink-faint)" }}
                title={c.pinned ? "Unpin" : `Pin to top (max ${maxPinned})`}
                onClick={(e) => {
                  e.stopPropagation();
                  onPin(c.id, !c.pinned);
                }}
              >
                <Icon name="bmark" size={13} />
              </button>
              <button
                style={iconBtn}
                title="Rename"
                onClick={(e) => {
                  e.stopPropagation();
                  startEdit(c);
                }}
              >
                <Icon name="pencil" size={13} />
              </button>
              <button
                style={iconBtn}
                title="Delete"
                onClick={(e) => {
                  e.stopPropagation();
                  setConfirmDel(c.id);
                }}
              >
                <Icon name="x" size={13} />
              </button>
            </span>
          </div>
        )}

        {isConfirm && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
            <span style={{ fontSize: 11.5, color: "var(--danger)" }}>Delete this chat?</span>
            <span style={{ flex: 1 }} />
            <button
              style={{ ...iconBtn, width: "auto", padding: "0 8px", color: "var(--danger)", fontSize: 11.5, fontWeight: 600 }}
              onClick={(e) => {
                e.stopPropagation();
                setConfirmDel(null);
                onDelete(c.id);
              }}
            >
              Delete
            </button>
            <button
              style={{ ...iconBtn, width: "auto", padding: "0 8px", fontSize: 11.5 }}
              onClick={(e) => {
                e.stopPropagation();
                setConfirmDel(null);
              }}
            >
              Cancel
            </button>
          </div>
        )}
      </div>
    );
  };

  return (
    <aside
      style={{
        flex: "none",
        width: 256,
        display: "flex",
        flexDirection: "column",
        background: "var(--surface-sunk)",
        borderRight: "1px solid var(--border)",
        minHeight: 0,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 10, padding: "13px 12px 10px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontFamily: "var(--serif)", fontWeight: 600, fontSize: 14.5 }}>Conversations</span>
          <span style={{ flex: 1 }} />
          <button style={iconBtn} title="Hide" onClick={onToggleCollapse}>
            <Icon name="chevL" size={15} />
          </button>
        </div>
        <button
          onClick={onNew}
          title="Start a new conversation"
          className="h-accent-deep"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 7,
            width: "100%",
            height: 34,
            background: "var(--accent)",
            color: "var(--accent-ink)",
            border: 0,
            borderRadius: 9,
            cursor: "pointer",
            fontSize: 13,
            fontWeight: 600,
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <Icon name="plus" size={15} />
          New chat
        </button>
      </div>

      <div style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "2px 8px 14px" }}>
        {conversations.length === 0 && (
          <p style={{ fontSize: 12, color: "var(--ink-muted)", padding: "8px 6px", lineHeight: 1.5 }}>
            No conversations yet. Ask a question — each thread is saved here.
          </p>
        )}
        {pinned.length > 0 && (
          <>
            <div style={labelStyle}>Pinned · {pinned.length}/{maxPinned}</div>
            {pinned.map(row)}
          </>
        )}
        {rest.length > 0 && (
          <>
            {pinned.length > 0 && <div style={{ ...labelStyle, marginTop: 12 }}>Recent</div>}
            {rest.map(row)}
          </>
        )}
      </div>
    </aside>
  );
}
