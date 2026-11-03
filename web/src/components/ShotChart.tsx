import type { Shot } from "@/lib/types";

// Court geometry in centimetres (FIBA). Feed coordinates have the basket at (0,0);
// y is shifted so the baseline sits at the top of the drawing.
const BASELINE = 157.5;
const W = 1500;
const H = 1000; // 10 m from the baseline; deep heaves are clipped
const tx = (x: number) => x + W / 2;
const ty = (y: number) => y + BASELINE;

/** Shot map. Each shot drops in (CSS, staggered) so the chart fills like a game replay. */
export function ShotChart({ shots }: { shots: Shot[] }) {
  const corner = Math.sqrt(675 ** 2 - 660 ** 2);
  const made = shots.filter((s) => s.made).length;
  return (
    <figure className="panel overflow-hidden p-0">
      <svg viewBox={`0 0 ${W} ${H}`} className="block w-full" role="img" aria-label={`Şut haritası: ${shots.length} şut, ${made} isabet`}>
        <defs>
          <pattern id="boards" width="120" height="1000" patternUnits="userSpaceOnUse">
            <rect width="120" height="1000" fill="var(--court)" />
            <line x1="0" x2="0" y1="0" y2="1000" stroke="rgb(255 255 255 / 0.035)" strokeWidth="3" />
          </pattern>
          <radialGradient id="glow" cx="50%" cy="10%" r="70%">
            <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.12" />
            <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
          </radialGradient>
        </defs>
        <rect width={W} height={H} fill="url(#boards)" />
        <rect width={W} height={H} fill="url(#glow)" />
        <g fill="none" stroke="var(--court-line)" strokeWidth={5}>
          <rect x={tx(-245)} y={0} width={490} height={580} fill="rgb(240 122 43 / 0.05)" />
          <circle cx={tx(0)} cy={580} r={180} />
          <path d={`M ${tx(-660)} 0 L ${tx(-660)} ${ty(corner)} A 675 675 0 0 0 ${tx(660)} ${ty(corner)} L ${tx(660)} 0`} />
          <path d={`M ${tx(-125)} ${ty(0)} A 125 125 0 0 0 ${tx(125)} ${ty(0)}`} />
          <line x1={tx(-90)} x2={tx(90)} y1={ty(-37.5)} y2={ty(-37.5)} strokeWidth={8} />
          <circle cx={tx(0)} cy={ty(0)} r={22.5} stroke="var(--accent)" />
        </g>
        {shots
          .filter((s) => ty(s.y) < H)
          .map((s, i) =>
            s.made ? (
              <circle key={i} className="drop" style={{ ["--i" as string]: i }} cx={tx(s.x)} cy={ty(s.y)} r={17}
                fill="var(--make)" fillOpacity={0.85} stroke="var(--bg)" strokeWidth={3} />
            ) : (
              <g key={i} className="drop" style={{ ["--i" as string]: i }} stroke="var(--miss)" strokeWidth={6} strokeOpacity={0.75} strokeLinecap="round">
                <line x1={tx(s.x) - 12} y1={ty(s.y) - 12} x2={tx(s.x) + 12} y2={ty(s.y) + 12} />
                <line x1={tx(s.x) - 12} y1={ty(s.y) + 12} x2={tx(s.x) + 12} y2={ty(s.y) - 12} />
              </g>
            ),
          )}
      </svg>
      <figcaption className="flex gap-5 border-t border-line px-4 py-2.5 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--make)" }} /> İsabet {made}
        </span>
        <span className="flex items-center gap-1.5">
          <span style={{ color: "var(--miss)" }}>✕</span> Kaçan {shots.length - made}
        </span>
      </figcaption>
    </figure>
  );
}
