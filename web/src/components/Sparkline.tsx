interface SparklineProps {
  values: number[];
  width: number;
  height: number;
  color: string;
  /** "max": scale against max only (book cards). "range": min–max normalized (KPI tiles). */
  scale?: "max" | "range";
}

export function Sparkline({ values, width, height, color, scale = "range" }: SparklineProps) {
  const viewH = scale === "max" ? 28 : 26;
  let points: string;
  if (scale === "max") {
    const max = Math.max(...values);
    points = values
      .map((v, i) => `${(i / (values.length - 1)) * 100},${28 - (v / max) * 24}`)
      .join(" ");
  } else {
    const max = Math.max(...values);
    const min = Math.min(...values);
    points = values
      .map(
        (v, i) =>
          `${((i / (values.length - 1)) * 100).toFixed(1)},${(viewH - ((v - min) / (max - min || 1)) * viewH).toFixed(1)}`,
      )
      .join(" ");
  }
  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 100 ${viewH}`}
      preserveAspectRatio="none"
      style={{ overflow: "visible" }}
    >
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={2.5}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
