import type { CSSProperties, ReactNode } from "react";
import { Fragment } from "react";
import { Icon } from "../icons";
import { pathChipSmStyle, pathChipStyle, seg, sepStyle } from "../ui";

export interface PathSeg {
  kind: "domain" | "shelf" | "book" | "page";
  label: ReactNode;
  /** page segments in citations show the page icon instead of a dot */
  pageIcon?: boolean;
  /** domain/shelf/book segments may show a colored dot */
  dot?: boolean;
}

const KIND_COLOR = {
  domain: "var(--domain)",
  shelf: "var(--shelf)",
  book: "var(--book)",
  page: "var(--page)",
} as const;

export function Dot({ color }: { color: string }) {
  return (
    <span style={{ width: 7, height: 7, borderRadius: "50%", background: color, flex: "none" }} />
  );
}

export function Seg({ s }: { s: PathSeg }) {
  return (
    <span style={seg(KIND_COLOR[s.kind])}>
      {s.pageIcon && (
        <span style={{ color: "var(--page)", display: "flex" }}>
          <Icon name="page" size={13} />
        </span>
      )}
      {s.dot && <Dot color={KIND_COLOR[s.kind]} />}
      {s.label}
    </span>
  );
}

interface PathChipProps {
  segs: PathSeg[];
  small?: boolean;
  onClick?: () => void;
  title?: string;
  trailing?: ReactNode;
  style?: CSSProperties;
  hover?: boolean;
}

export function PathChip({ segs, small, onClick, title, trailing, style, hover }: PathChipProps) {
  const base = small ? pathChipSmStyle : pathChipStyle;
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      onClick={onClick}
      title={title}
      className={hover ? "h-chip" : undefined}
      style={{ ...base, ...(onClick ? { cursor: "pointer" } : { cursor: "default" }), ...style }}
    >
      {segs.map((s, i) => (
        <Fragment key={i}>
          {i > 0 && <span style={sepStyle}>▸</span>}
          <Seg s={s} />
        </Fragment>
      ))}
      {trailing}
    </Tag>
  );
}
