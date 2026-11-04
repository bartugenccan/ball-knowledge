import { heatVar } from "@/lib/format";

const ROWS = 20;
const AISLE = 5; // degrees between sections

type Axis = { label: string; value: number; note?: string };

const polar = (c: number, r: number, deg: number) => {
  const a = (deg * Math.PI) / 180;
  return [c + r * Math.cos(a), c + r * Math.sin(a)] as const;
};

const arc = (c: number, r: number, a0: number, a1: number) => {
  const [x0, y0] = polar(c, r, a0);
  const [x1, y1] = polar(c, r, a1);
  return `M${x0.toFixed(1)} ${y0.toFixed(1)}A${r.toFixed(1)} ${r.toFixed(1)} 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`;
};

/**
 * Player profile drawn as an arena seen from above: six stand sections around the court, 20
 * rows of seats in each, filled from the court outward up to the rating. Head-to-head, each
 * section splits in two along its middle aisle, like opposing fans sharing a stand.
 *
 * Rows of one colour share a single path, so a chart is a few dozen nodes, not 240.
 */
export function ArenaChart({ values, compare, center, className = "" }: { values: Axis[]; compare?: Axis[]; center?: number; className?: string }) {
  const size = 480;
  const c = size / 2;
  const r0 = 62;
  const R = 176;
  const rowH = (R - r0) / ROWS;
  const n = values.length;
  const span = 360 / n;
  const stroke = rowH * 0.72;
  const dash = `${(rowH * 0.74).toFixed(2)} ${(rowH * 0.2).toFixed(2)}`;

  const seats = (key: string, s: number, val: number, a0: number, a1: number, color?: string) => {
    const lit = Math.round(val);
    const byColor = new Map<string, string[]>();
    const off: string[] = [];
    for (let row = 0; row < ROWS; row++) {
      const d = arc(c, r0 + rowH * (row + 0.5), a0, a1);
      if (row + 1 > lit) off.push(d);
      else {
        const k = color ?? heatVar(row + 1);
        byColor.set(k, [...(byColor.get(k) ?? []), d]);
      }
    }
    return (
      <>
        <path d={off.join("")} fill="none" strokeWidth={stroke} strokeDasharray={dash} stroke="var(--seat-off)" />
        <g className="seat-group" style={{ ["--s" as string]: s }}>
          {[...byColor].map(([k, parts]) => (
            <path key={`${key}${k}`} d={parts.join("")} fill="none" strokeWidth={stroke} strokeDasharray={dash} stroke={k} />
          ))}
        </g>
      </>
    );
  };

  return (
    <svg
      viewBox={`-58 -6 ${size + 116} ${size + 12}`}
      className={`arena w-full ${className}`}
      role="img"
      aria-label={values.map((v, i) => `${v.label} ${v.value.toFixed(0)}${compare ? ` / ${compare[i].value.toFixed(0)}` : ""}`).join(", ")}
    >
      {values.map((v, i) => {
        const mid = -90 + i * span;
        const a0 = mid - span / 2 + AISLE / 2;
        const a1 = mid + span / 2 - AISLE / 2;
        const [lx, ly] = polar(c, R + 22, mid);
        const anchor = Math.abs(lx - c) < 12 ? "middle" : lx > c ? "start" : "end";
        const w = compare?.[i];
        return (
          <g key={v.label} className="arena-sector">
            {v.note && <title>{v.note}</title>}
            {w ? (
              <>
                {seats("a", i, v.value, a0, mid - 1, "var(--side-a)")}
                {seats("b", i, w.value, mid + 1, a1, "var(--side-b)")}
              </>
            ) : (
              seats("s", i, v.value, a0, a1)
            )}
            <text x={lx} y={ly - 5} textAnchor={anchor} fontSize={16} fill="var(--muted)">{v.label}</text>
            <text x={lx} y={ly + 17} textAnchor={anchor} fontSize={23} fontWeight={800} fill="var(--ink)" style={{ fontFamily: "var(--font-display)" }}>
              {w ? (
                <>
                  <tspan fill="var(--side-a-t)">{v.value.toFixed(0)}</tspan>
                  <tspan fill="var(--dim)"> : </tspan>
                  <tspan fill="var(--side-b-t)">{w.value.toFixed(0)}</tspan>
                </>
              ) : (
                v.value.toFixed(0)
              )}
            </text>
          </g>
        );
      })}
      {center !== undefined ? (
        <text x={c} y={c + 21} textAnchor="middle" fontSize={62} fontWeight={900} fill="var(--ink)" style={{ fontFamily: "var(--font-display)" }}>
          {center}
        </text>
      ) : (
        // the court in the middle of the bowl
        <g fill="none" stroke="var(--ink)" strokeWidth={2}>
          <rect x={c - 44} y={c - 24} width={88} height={48} />
          <line x1={c} x2={c} y1={c - 24} y2={c + 24} />
          <circle cx={c} cy={c} r={8} />
        </g>
      )}
    </svg>
  );
}
