"use client";

import { useRef, useState } from "react";

const W = 860;
const H = 280;
const PAD = { l: 44, r: 16, t: 18, b: 26 };
const MINUTES = 40;

type Line = { key: string; label: string; values: number[]; color: string; width: number; dash?: string };

/** The score margin minute by minute: the range the model expected, one scenario and, if played, the real game. */
export function MarginChart({ home, away, band, lines }: {
  home: string; away: string; band: { lo: number[]; hi: number[] }; lines: Line[];
}) {
  const ref = useRef<SVGSVGElement>(null);
  const [minute, setMinute] = useState<number | null>(null);
  const peak = Math.max(10, ...band.hi.map(Math.abs), ...band.lo.map(Math.abs), ...lines.flatMap((l) => l.values.map(Math.abs)));
  const top = Math.ceil(peak / 5) * 5;
  const x = (m: number) => PAD.l + (m / MINUTES) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + ((top - v) / (2 * top)) * (H - PAD.t - PAD.b);
  const path = (v: number[]) => v.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(p).toFixed(1)}`).join(" ");
  const area = `${path(band.hi)} ${band.lo.map((p, i) => [i, p] as const).reverse().map(([i, p]) => `L${x(i).toFixed(1)} ${y(p).toFixed(1)}`).join(" ")} Z`;
  // built outward from zero, so the line that matters always has a tick
  const step = top > 20 ? 10 : 5;
  const ticks: number[] = [0];
  for (let v = step; v <= top; v += step) ticks.push(v, -v);

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box) return;
    const px = ((e.clientX - box.left) / box.width) * W;
    setMinute(Math.max(0, Math.min(MINUTES, Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * MINUTES))));
  };
  const lead = (v: number) => (v === 0 ? "Beraberlik" : `${v > 0 ? home : away} +${Math.abs(v).toFixed(0)}`);

  return (
    <figure className="space-y-2">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-muted">
        <span className="flex items-center gap-1.5"><span className="h-3 w-5 rounded-sm bg-[color-mix(in_oklab,var(--muted)_28%,transparent)]" />Beklenen aralık (%80)</span>
        {lines.map((l) => (
          <span key={l.key} className="flex items-center gap-1.5">
            <svg width="22" height="6" aria-hidden="true"><line x1="0" x2="22" y1="3" y2="3" stroke={l.color} strokeWidth={l.width} strokeDasharray={l.dash} /></svg>
            {l.label}
          </span>
        ))}
      </div>
      {/* on a phone the axis text would shrink past reading size, so the chart scrolls instead */}
      <div className="overflow-x-auto">
      <div className="relative min-w-[620px]">
        <svg
          ref={ref} viewBox={`0 0 ${W} ${H}`} className="w-full touch-pan-y" role="img"
          aria-label={`${home} ve ${away} arasındaki skor farkının dakika dakika seyri`}
          onPointerMove={onMove} onPointerLeave={() => setMinute(null)}
        >
          {ticks.map((v) => (
            <g key={v}>
              <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke={v === 0 ? "var(--dim)" : "var(--line)"} strokeWidth={v === 0 ? 1.5 : 1} />
              <text x={PAD.l - 6} y={y(v) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{v === 0 ? "0" : `+${Math.abs(v)}`}</text>
            </g>
          ))}
          {[10, 20, 30].map((m) => <line key={m} x1={x(m)} x2={x(m)} y1={PAD.t} y2={H - PAD.b} stroke="var(--line)" strokeWidth={1} />)}
          {[0, 1, 2, 3].map((q) => (
            <text key={q} x={x(q * 10 + 5)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--muted)">{q + 1}. çeyrek</text>
          ))}
          <text x={PAD.l + 4} y={PAD.t + 10} fontSize="11" fontWeight="700" fill="var(--side-a-t)">{home} önde</text>
          <text x={PAD.l + 4} y={H - PAD.b - 5} fontSize="11" fontWeight="700" fill="var(--side-b-t)">{away} önde</text>
          <path d={area} fill="color-mix(in oklab, var(--muted) 28%, transparent)" />
          {lines.map((l) => (
            <path key={l.key} d={path(l.values)} fill="none" stroke={l.color} strokeWidth={l.width} strokeDasharray={l.dash} strokeLinejoin="round" strokeLinecap="round" />
          ))}
          {minute !== null && (
            <g pointerEvents="none">
              <line x1={x(minute)} x2={x(minute)} y1={PAD.t} y2={H - PAD.b} stroke="var(--ink)" strokeWidth={1} />
              {lines.map((l) => <circle key={l.key} cx={x(minute)} cy={y(l.values[minute] ?? 0)} r={4} fill={l.color} stroke="var(--bg)" strokeWidth={2} />)}
            </g>
          )}
        </svg>
        {minute !== null && (
          <div
            className="pointer-events-none absolute top-2 z-10 rounded-md border border-line bg-panel px-2.5 py-1.5 text-xs shadow-lg"
            style={minute > 26 ? { right: `${100 - (100 * x(minute)) / W + 1.5}%` } : { left: `${(100 * x(minute)) / W + 1.5}%` }}
          >
            <p className="font-semibold">{minute}. dakika</p>
            {lines.map((l) => <p key={l.key} className="whitespace-nowrap text-muted">{l.label}: <span className="text-ink">{lead(l.values[minute] ?? 0)}</span></p>)}
            <p className="whitespace-nowrap text-muted">Aralık: <span className="text-ink">{lead(band.lo[minute])} / {lead(band.hi[minute])}</span></p>
          </div>
        )}
      </div>
      </div>
    </figure>
  );
}
