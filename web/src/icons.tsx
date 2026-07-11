// Icon set ported verbatim from the design file's icon factory.
import type { CSSProperties, ReactElement } from "react";

export type IconName =
  | "ask"
  | "library"
  | "ingest"
  | "observatory"
  | "settings"
  | "sun"
  | "moon"
  | "book"
  | "shelf"
  | "domain"
  | "toc"
  | "page"
  | "owl"
  | "check"
  | "return"
  | "search"
  | "send"
  | "stop"
  | "copy"
  | "thumbup"
  | "thumbdown"
  | "sparkle"
  | "inboxplus"
  | "x"
  | "chevL"
  | "chevR"
  | "chevDown"
  | "foot"
  | "dot"
  | "bmark"
  | "alert";

interface IconProps {
  name: IconName;
  size?: number;
  sw?: number;
  style?: CSSProperties;
}

export function Icon({ name, size = 18, sw = 1.7, style }: IconProps): ReactElement {
  const stroke = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: sw,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  } as const;
  const P = (d: string, key?: string) => <path key={key ?? d} d={d} {...stroke} />;
  const C = (cx: number, cy: number, r: number, fill = false, key?: string) => (
    <circle
      key={key ?? `c${cx}-${cy}-${r}`}
      cx={cx}
      cy={cy}
      r={r}
      fill={fill ? "currentColor" : "none"}
      stroke={fill ? "none" : "currentColor"}
      strokeWidth={sw}
    />
  );
  const R = (x: number, y: number, w: number, h: number, rx: number, key?: string) => (
    <rect key={key ?? `r${x}-${y}`} x={x} y={y} width={w} height={h} rx={rx} {...stroke} />
  );
  const L = (x1: number, y1: number, x2: number, y2: number, key?: string) => (
    <line
      key={key ?? `l${x1}-${y1}-${x2}-${y2}`}
      x1={x1}
      y1={y1}
      x2={x2}
      y2={y2}
      stroke="currentColor"
      strokeWidth={sw}
      strokeLinecap="round"
    />
  );

  const body = (): ReactElement[] => {
    switch (name) {
      case "ask":
        return [P("M4 5h16v11H8l-4 4z")];
      case "library":
        return [R(4, 4, 4, 16, 1), R(10, 4, 4, 16, 1), P("M17 5.2l3.5 1 -3 14.5 -3.5-1z")];
      case "ingest":
        return [
          P("M4 13v5a1 1 0 001 1h14a1 1 0 001-1v-5"),
          P("M4 13h4l1 2h6l1-2h4"),
          P("M12 3v7m0 0l-2.5-2.5M12 10l2.5-2.5"),
        ];
      case "observatory":
        return [
          P("M4 20l6-8"),
          P("M3.5 12.8l4.5-6.2 8.2 5-4.5 6.2z"),
          L(16.2, 11.6, 20, 9),
          C(19, 7.5, 1.4),
        ];
      case "settings":
        return [
          C(12, 12, 3),
          P("M12 3v2.5M12 18.5V21M4.2 7l2.1 1.2M17.7 15.8l2.1 1.2M4.2 17l2.1-1.2M17.7 8.2l2.1-1.2"),
        ];
      case "sun":
        return [
          C(12, 12, 4),
          P("M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"),
        ];
      case "moon":
        return [P("M20 14.5A8 8 0 019.5 4 7 7 0 1020 14.5z")];
      case "book":
        return [P("M6 4h11a1 1 0 011 1v15H7a1 1 0 01-1-1z"), P("M6 4a2 2 0 00-2 2v13a2 2 0 012-2")];
      case "shelf":
        return [R(3, 15, 18, 5, 1), L(6, 15, 6, 7), L(9, 15, 9, 7), P("M12 15V8l3-.6 .6 7.6")];
      case "domain":
        return [
          P("M4 9l8-4 8 4"),
          L(5, 9, 5, 18),
          L(9.7, 9, 9.7, 18),
          L(14.3, 9, 14.3, 18),
          L(19, 9, 19, 18),
          L(3.5, 18.5, 20.5, 18.5),
        ];
      case "toc":
        return [
          L(9, 6, 20, 6),
          L(9, 12, 20, 12),
          L(9, 18, 20, 18),
          C(5, 6, 1, true),
          C(5, 12, 1, true),
          C(5, 18, 1, true),
        ];
      case "page":
        return [P("M6 3h8l4 4v14H6z"), P("M14 3v4h4"), L(9, 13, 15, 13), L(9, 16.5, 13, 16.5)];
      case "owl":
        return [
          C(9, 10, 2.4),
          C(15, 10, 2.4),
          P("M6 7a6 6 0 0112 0v5a6 6 0 01-12 0z"),
          P("M10.6 13.2l1.4 1.2 1.4-1.2"),
          P("M6.5 6l-2-2M17.5 6l2-2"),
        ];
      case "check":
        return [P("M5 12.5l4.5 4.5L19 7")];
      case "return":
        return [P("M9 7L4 12l5 5"), P("M4 12h10a5 5 0 015 5v1")];
      case "search":
        return [C(11, 11, 6), L(15.5, 15.5, 20, 20)];
      case "send":
        return [<path key="s" d="M5 12h13M12 5l7 7-7 7" {...stroke} strokeWidth={2} />];
      case "stop":
        return [R(7, 7, 10, 10, 2)];
      case "copy":
        return [R(9, 9, 11, 11, 2), P("M5 15V5a1 1 0 011-1h9")];
      case "thumbup":
        return [P("M7 11v9H4v-9zM7 11l4-7a2 2 0 012 2v3h5a2 2 0 012 2l-1.5 6a2 2 0 01-2 1.5H7")];
      case "thumbdown":
        return [P("M17 13V4h3v9zM17 13l-4 7a2 2 0 01-2-2v-3H6a2 2 0 01-2-2l1.5-6A2 2 0 017.5 4H17")];
      case "sparkle":
        return [
          P("M12 4l1.6 4.4L18 10l-4.4 1.6L12 16l-1.6-4.4L6 10l4.4-1.6z"),
          P("M18 15l.7 1.8L20.5 17.5l-1.8.7L18 20l-.7-1.8L15.5 17.5l1.8-.7z"),
        ];
      case "inboxplus":
        return [
          P("M4 13v5a1 1 0 001 1h14a1 1 0 001-1v-5"),
          P("M4 13h4l1 2h6l1-2h4"),
          P("M12 3v6m-3-3h6"),
        ];
      case "x":
        return [<path key="x" d="M6 6l12 12M18 6L6 18" {...stroke} strokeWidth={2} />];
      case "chevL":
        return [<path key="cl" d="M14 6l-6 6 6 6" {...stroke} strokeWidth={2} />];
      case "chevR":
        return [<path key="cr" d="M9 6l6 6-6 6" {...stroke} strokeWidth={2} />];
      case "chevDown":
        return [<path key="cd" d="M6 9l6 6 6-6" {...stroke} strokeWidth={2} />];
      case "foot":
        return [
          P("M8 6a3 3 0 013 3c0 3-2 4-2 7H6c0-2-2-3-2-6a2 2 0 014-1"),
          C(14, 5, 1.2),
          C(16.5, 6, 1),
          C(18.5, 8, 0.9),
        ];
      case "dot":
        return [C(12, 12, 3, true)];
      case "bmark":
        return [P("M7 4h10v16l-5-4-5 4z")];
      case "alert":
        return [P("M12 4l9 16H3z"), L(12, 10, 12, 15), C(12, 17.6, 0.3, true)];
    }
  };

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      aria-hidden
      style={{ display: "block", flex: "none", ...style }}
    >
      {body()}
    </svg>
  );
}
