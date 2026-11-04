"use client";

import { useRouter } from "next/navigation";
import { memo, useMemo, useState } from "react";
import { InView } from "@/components/motion/InView";
import { clubVars } from "@/lib/clubs";
import { tone } from "@/lib/format";

type P = { id: string; name: string; team: string; vals: Record<string, number> };
const SCALE = Array.from({ length: 20 }, (_, i) => i + 1);
const PER_COL = 3;

/**
 * Cards are memoised as one block: pointing at a card only updates the readout above, it never
 * re-renders 244 anchors. Plain anchors with one delegated click handler instead of 244 Links.
 */
const Cards = memo(function Cards({ players, seats, label }: { players: P[]; seats: Map<string, { x: number; y: number; v: number }>; label?: string }) {
  return (
    <>
      {players.map((p, i) => {
        const s = seats.get(p.id)!;
        return (
          <a
            key={p.id}
            href={`/players/${p.id}`}
            tabIndex={-1}
            aria-label={`${p.name}, ${label} ${s.v}`}
            data-pid={p.id}
            className="crowd-tile in"
            style={{
              ["--club-l" as string]: clubVars(p.team)?.["--club-l"] ?? "#141414",
              ["--club-d" as string]: clubVars(p.team)?.["--club-d"] ?? "#efefe9",
              ["--x" as string]: s.x,
              ["--y" as string]: s.y,
              // everyone sets off at a slightly different moment
              ["--j" as string]: (i * 37) % 260,
              ["--d" as string]: s.v * 3 + s.y,
            }}
          />
        );
      })}
    </>
  );
});

/**
 * The whole league as a crowd: one card per player in their club's colour, stacked over their rating. Choose another
 * attribute and everyone walks to a new seat. Positions are CSS custom properties, so the move
 * is a compositor transition and React only touches the numbers.
 */
export function LeagueCrowd({ players, attrs }: { players: P[]; attrs: { key: string; label: string }[] }) {
  const router = useRouter();
  const [attr, setAttr] = useState(attrs[0].key);
  const [activeId, setActiveId] = useState<string | null>(null);

  const { seats, rows, leader } = useMemo(() => {
    const filled = new Map<number, number>();
    const out = new Map<string, { x: number; y: number; v: number }>();
    let best: P | undefined;
    for (const p of players) {
      const v = Math.max(1, Math.min(20, Math.round(p.vals[attr] ?? 1)));
      const n = filled.get(v) ?? 0;
      filled.set(v, n + 1);
      out.set(p.id, { x: (v - 1) * (PER_COL + 0.1) + (n % PER_COL), y: Math.floor(n / PER_COL), v });
      if (!best || (p.vals[attr] ?? 0) > (best.vals[attr] ?? 0)) best = p;
    }
    const tallest = Math.max(1, ...[...filled.values()].map((n) => Math.ceil(n / PER_COL)));
    return { seats: out, rows: tallest, leader: best };
  }, [players, attr]);

  const shown = players.find((p) => p.id === activeId) ?? leader;
  const label = attrs.find((a) => a.key === attr)?.label;

  return (
    <div>
      <div className="mb-5 flex flex-wrap gap-x-5 gap-y-1" role="tablist" aria-label="Özellik">
        {attrs.map((a) => (
          <button key={a.key} type="button" role="tab" aria-selected={a.key === attr} className="tab" onClick={() => setAttr(a.key)}>
            {a.label}
          </button>
        ))}
      </div>
      <p className="mb-3 flex min-h-9 flex-wrap items-baseline gap-x-3" aria-live="polite">
        {shown && (
          <>
            <span className={`num text-3xl ${tone(shown.vals[attr] ?? 1)}`}>{shown.vals[attr]}</span>
            <span lang="en" className="display text-xl">{shown.name}</span>
            <span className="text-sm text-muted">{shown.team}, {label}</span>
          </>
        )}
      </p>
      <InView amount={0.15} className="crowd">
        <div
          className="crowd-field"
          style={{ ["--rows" as string]: rows }}
          onPointerOver={(e) => {
            const id = (e.target as HTMLElement).dataset?.pid;
            if (id && id !== activeId) setActiveId(id);
          }}
          onPointerLeave={() => setActiveId(null)}
          onClick={(e) => {
            const a = (e.target as HTMLElement).closest("a");
            // let the browser handle new-tab clicks; everything else is a normal client navigation
            if (!a || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
            e.preventDefault();
            router.push(a.getAttribute("href")!);
          }}
        >
          <Cards players={players} seats={seats} label={label} />
        </div>
        <div className="mt-2 grid border-t-2 border-ink pt-1.5" style={{ gridTemplateColumns: "repeat(20, minmax(0, 1fr))" }}>
          {SCALE.map((v) => (
            <span key={v} className={`num text-center text-[10px] sm:text-sm ${tone(v)}`}>{v}</span>
          ))}
        </div>
      </InView>
    </div>
  );
}
