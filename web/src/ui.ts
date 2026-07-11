// Shared style factories — ported from the design file's renderVals() helpers.
import type { CSSProperties } from "react";

export const seg = (color: string): CSSProperties => ({
  display: "inline-flex",
  alignItems: "center",
  gap: 5,
  color,
  fontWeight: 600,
  whiteSpace: "nowrap",
});

export const sepStyle: CSSProperties = { color: "var(--ink-faint)", fontSize: 11, opacity: 0.7 };

export const badge = (c: string, cw: string): CSSProperties => ({
  display: "inline-flex",
  alignItems: "center",
  gap: 5,
  padding: "2px 9px",
  borderRadius: 20,
  fontSize: 11.5,
  fontWeight: 600,
  color: c,
  background: cw,
  fontFamily: "var(--sans)",
});

export const chip = (c: string, cw: string): CSSProperties => ({
  display: "inline-flex",
  alignItems: "center",
  gap: 5,
  padding: "2px 8px",
  borderRadius: 6,
  fontSize: 11,
  fontWeight: 600,
  color: c,
  background: cw,
});

export const pathChipStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 7,
  padding: "7px 12px",
  background: "var(--surface-sunk)",
  border: "1px solid var(--border)",
  borderRadius: 9,
  fontSize: 12.5,
  cursor: "pointer",
  fontFamily: "var(--sans)",
  flexWrap: "wrap",
};

export const pathChipSmStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  padding: "5px 10px",
  background: "var(--surface-sunk)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
};

export const actionBtnStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  padding: "7px 11px",
  background: "transparent",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12.5,
  color: "var(--ink-muted)",
  cursor: "pointer",
  fontFamily: "var(--sans)",
};

export const iconBtnStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: 34,
  height: 34,
  background: "transparent",
  border: "1px solid var(--border)",
  borderRadius: 8,
  color: "var(--ink-muted)",
  cursor: "pointer",
};

export const ghostBtnStyle: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 12,
  padding: "10px 12px",
  borderRadius: 10,
  cursor: "pointer",
  border: 0,
  background: "transparent",
  color: "var(--ink-muted)",
  font: "500 13.5px/1 var(--sans)",
  width: "100%",
  textAlign: "left",
};

export const primaryBtnStyle: CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 7,
  padding: "9px 16px",
  background: "var(--accent)",
  color: "var(--accent-ink)",
  border: 0,
  borderRadius: 9,
  fontSize: 13,
  fontWeight: 600,
  cursor: "pointer",
};

export const nodeCardStyle = (active: boolean): CSSProperties => ({
  position: "relative",
  textAlign: "left",
  width: "100%",
  background: "var(--surface-raised)",
  border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
  borderLeft: `3px solid ${active ? "var(--accent)" : "transparent"}`,
  borderRadius: 11,
  padding: "13px 15px",
  cursor: "pointer",
  boxShadow: active ? "var(--shadow-sm)" : "none",
  transition: "border-color .12s",
});

export const sectionLabelStyle: CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: ".07em",
  textTransform: "uppercase",
  color: "var(--ink-faint)",
};

export const answerCardStyle: CSSProperties = {
  background: "var(--surface-raised)",
  border: "1px solid var(--border)",
  borderRadius: 14,
  padding: "20px 22px",
  boxShadow: "var(--shadow-sm)",
};

export const KIND_META = {
  domain: { label: "Domain", color: "var(--domain)" },
  shelf: { label: "Shelf", color: "var(--shelf)" },
  book: { label: "Book", color: "var(--book)" },
  toc: { label: "Contents", color: "var(--ink-muted)" },
  page: { label: "Page", color: "var(--page)" },
} as const;

export type StepKind = keyof typeof KIND_META;

export const kindIconName = (k: StepKind): "toc" | "domain" | "shelf" | "book" | "page" =>
  k === "toc" ? "toc" : k;
