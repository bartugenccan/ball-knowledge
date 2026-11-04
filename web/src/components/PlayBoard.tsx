import { COURT_H, COURT_W, CourtLines, tx, ty } from "@/components/Court";
import { InView } from "@/components/motion/InView";

type Pt = readonly [number, number];

// Starting spots of the Horns Flare set in the engine's library, metres from the basket.
const POS: Record<string, [number, number]> = { "1": [0, 8], "2": [-6.6, 0.5], "3": [6.6, 0.5], "4": [-2.5, 6], "5": [2.5, 6] };
const q = (x: number, y: number): Pt => [tx(x * 100), ty(y * 100)];
const p = (k: string): Pt => q(POS[k][0], POS[k][1]);

/** `prev` is the last control point: it gives the direction the line arrives from. */
const MOVES: { d: string; prev: Pt; end: Pt; kind: "screen" | "arrow" }[] = [
  // 5 comes up to screen for 1
  { d: `M${p("5")} L${q(1, 7.4)}`, prev: p("5"), end: q(1, 7.4), kind: "screen" },
  // 1 drives off the screen
  { d: `M${p("1")} C${q(-1.4, 6.8)} ${q(-1.4, 3.6)} ${q(-0.5, 1.4)}`, prev: q(-1.4, 3.6), end: q(-0.5, 1.4), kind: "arrow" },
  // 4 flares for 2
  { d: `M${p("4")} L${q(-4.4, 3.9)}`, prev: p("4"), end: q(-4.4, 3.9), kind: "screen" },
  // 2 comes off the flare
  { d: `M${p("2")} C${q(-6.4, 2.6)} ${q(-6, 5)} ${q(-5.4, 6.6)}`, prev: q(-6, 5), end: q(-5.4, 6.6), kind: "arrow" },
];

/** Coaches' notation: a bar for a screen, an arrow for a cut. */
function tip({ prev, end, kind }: (typeof MOVES)[number]) {
  const a = Math.atan2(end[1] - prev[1], end[0] - prev[0]);
  const at = (d: number, side: number) => `${end[0] + d * Math.cos(a) - side * Math.sin(a)},${end[1] + d * Math.sin(a) + side * Math.cos(a)}`;
  return kind === "screen" ? `M${at(0, -38)} L${at(0, 38)}` : `M${at(-34, -26)} L${at(0, 0)} L${at(-34, 26)}`;
}

/** A coach's play sheet on a blue board. It draws itself, using the real starting spots of a set. */
export function PlayBoard({ className = "" }: { className?: string }) {
  return (
    <InView amount={0.3} className={className}>
      <svg viewBox={`0 0 ${COURT_W} ${COURT_H + 30}`} className="block w-full" role="img" aria-label="Horns Flare seti: 5 perde, 1 sürüyor, 4 flare perdesi, 2 çıkıyor">
        <CourtLines stroke="var(--chalk-2)" rim="var(--chalk)" paint="rgb(255 255 255 / 0.05)" />
        <g fill="none" stroke="var(--chalk)" strokeWidth={9} strokeLinecap="round" strokeLinejoin="round">
          {MOVES.map((m, i) => (
            <g key={m.d}>
              <path d={m.d} pathLength={1} className="draw" style={{ ["--i" as string]: i + 1 }} />
              <path d={tip(m)} className="chalk-in" style={{ ["--i" as string]: 8 + i * 4 }} />
            </g>
          ))}
        </g>
        {Object.keys(POS).map((k, i) => {
          const [x, y] = p(k);
          return (
            <g key={k} className="chalk-in" style={{ ["--i" as string]: i }}>
              <circle cx={x} cy={y} r={46} fill="var(--board)" stroke="var(--chalk)" strokeWidth={8} />
              <text x={x} y={y + 22} textAnchor="middle" fontSize={62} fontWeight={900} fill="var(--chalk)" style={{ fontFamily: "var(--font-display)" }}>{k}</text>
            </g>
          );
        })}
      </svg>
    </InView>
  );
}
