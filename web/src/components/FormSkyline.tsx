"use client";

import { useState } from "react";
import { InView } from "@/components/motion/InView";
import { gameTone } from "@/lib/format";
import type { GameLine } from "@/lib/types";

const ORDINARY = 6.6;
const LO = 3;
const HI = 10;

/**
 * Season form as a skyline around an ordinary night (6.6): good games rise above the line,
 * bad ones hang below it. Reads faster than a line chart, and a cold streak looks like one.
 */
export function FormSkyline({ games }: { games: GameLine[] }) {
  const [active, setActive] = useState<number | null>(null);
  if (games.length === 0) return <p className="text-sm text-muted">Bu sezon maç yok.</p>;
  const g = games[active ?? games.length - 1];
  const up = HI - ORDINARY;
  const down = ORDINARY - LO;
  const upPct = (up / (up + down)) * 100;

  return (
    <div>
      <p className="mb-3 flex min-h-[1.5rem] flex-wrap items-baseline gap-x-3 text-sm" aria-live="polite">
        <span className={`num text-xl ${gameTone(g.game_rating)}`}>{g.game_rating.toFixed(1)}</span>
        <span className="font-semibold">Tur {g.round ?? "?"} {g.is_home ? "vs" : "@"} {g.opponent}</span>
        <span className="text-muted">{g.pts} sayı, {g.orb + g.drb} ribaund, {g.ast} asist, {g.minutes.toFixed(0)} dk</span>
      </p>
      <InView amount={0.3}>
        <div className="relative h-44" onPointerLeave={() => setActive(null)}>
          <div className="absolute inset-x-0 h-[2px] bg-ink" style={{ top: `${upPct}%` }} />
          <div className="absolute inset-0 grid" style={{ gridTemplateColumns: `repeat(${games.length}, minmax(0, 1fr))` }}>
            {games.map((game, i) => {
              const v = Math.max(LO, Math.min(HI, game.game_rating));
              const above = v >= ORDINARY;
              const hPct = above ? ((v - ORDINARY) / (up + down)) * 100 : ((ORDINARY - v) / (up + down)) * 100;
              return (
                <button
                  key={game.gamecode}
                  type="button"
                  onPointerEnter={() => setActive(i)}
                  onFocus={() => setActive(i)}
                  onBlur={() => setActive(null)}
                  aria-label={`Tur ${game.round ?? "?"}, ${game.is_home ? "vs" : "@"} ${game.opponent}: ${game.game_rating.toFixed(1)}`}
                  className="relative h-full focus-visible:outline-offset-0"
                  style={{ background: active === i ? "color-mix(in srgb, var(--ink) 10%, transparent)" : undefined }}
                >
                  <span
                    className={`sky-bar ${above ? `heat-${gameTone(game.game_rating)}` : "bg-muted"} absolute inset-x-[12%]`}
                    style={{
                      height: `max(${hPct}%, 2px)`,
                      ...(above ? { bottom: `${100 - upPct}%`, ["--o" as string]: "bottom" } : { top: `${upPct}%`, ["--o" as string]: "top" }),
                      ["--i" as string]: i,
                    }}
                  />
                </button>
              );
            })}
          </div>
        </div>
      </InView>
      <p className="mt-2 text-xs text-dim">Kalın çizgi sıradan bir maçtır (6,6). Üstü iyi, altı kötü.</p>
    </div>
  );
}
