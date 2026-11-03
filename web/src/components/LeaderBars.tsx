"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { properName, tone } from "@/lib/format";
import type { PlayerRow } from "@/lib/types";

/** Ranked bars for a leader list; bar length is the 1–20 rating. */
export function LeaderBars({ players, attrKey }: { players: PlayerRow[]; attrKey: string }) {
  return (
    <ol className="mt-auto space-y-3 pt-8">
      {players.map((p, i) => {
        const v = Number(p[attrKey]);
        return (
          <li key={p.player_id}>
            <Link href={`/players/${p.player_id}`} className="group grid grid-cols-[1.25rem_1fr_auto] items-center gap-3 text-sm">
              <span className="font-display text-base font-bold text-dim">{i + 1}</span>
              <div className="relative h-11 overflow-hidden rounded-lg bg-bg-2/70">
                <motion.div
                  className={`fill-${tone(v)} absolute inset-y-0 left-0 w-full origin-left opacity-20 transition-opacity group-hover:opacity-35`}
                  initial={{ scaleX: 0 }}
                  whileInView={{ scaleX: v / 20 }}
                  viewport={{ once: true }}
                  transition={{ duration: 0.9, delay: 0.2 + i * 0.08, ease: [0.16, 1, 0.3, 1] }}
                />
                <span lang="en" className="relative flex h-full items-center gap-2 px-3">
                  <span className="truncate font-medium">{properName(p.player)}</span>
                  <span className="text-xs text-dim">{p.team}</span>
                </span>
              </div>
              <span className={`w-7 text-right font-display text-2xl font-bold ${tone(v)}`}>{v}</span>
            </Link>
          </li>
        );
      })}
    </ol>
  );
}
