"use client";

import { motion } from "motion/react";
import { useState } from "react";
import { AttributeCard } from "@/components/AttributeCard";
import { monthLabel } from "@/lib/format";
import type { AttributeMeta, Rating } from "@/lib/types";

/** Season vs. monthly view of the attribute card; month view shows change vs. season. */
export function RatingsWindow({
  attributes,
  season,
  months,
}: {
  attributes: AttributeMeta[];
  season: Rating[];
  months: { month: string; games: number; ratings: Rating[] }[];
}) {
  const [win, setWin] = useState<string>("season");
  const month = months.find((m) => m.month === win);
  const tabs = [{ id: "season", label: "Sezon", games: undefined as number | undefined }, ...months.map((m) => ({ id: m.month, label: monthLabel(m.month), games: m.games }))];
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="font-display text-2xl font-bold uppercase tracking-wide">Özellikler</h2>
        <div className="flex flex-wrap gap-1 rounded-full border border-line bg-bg-2 p-1 text-sm" role="tablist">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              role="tab"
              aria-selected={win === t.id}
              onClick={() => setWin(t.id)}
              className={`relative isolate rounded-full px-3 py-1 transition-colors ${win === t.id ? "text-accent-ink" : "text-muted hover:text-ink"}`}
            >
              {win === t.id && (
                <motion.span layoutId="ratings-window" className="absolute inset-0 -z-10 rounded-full bg-accent"
                  transition={{ type: "spring", stiffness: 400, damping: 34 }} />
              )}
              {t.label}
              {t.games !== undefined && <span className="ml-1 text-xs opacity-70">{t.games} maç</span>}
            </button>
          ))}
        </div>
      </div>
      <AttributeCard attributes={attributes} ratings={month ? month.ratings : season} compare={month ? season : undefined} windowKey={win} />
      {month && (
        <p className="text-xs text-dim">
          Aylık puanlar sezonla aynı ölçekte. Az maç olduğu için ortalamaya daha çok çekilirler. Küçük renkli sayı sezona göre farkı gösterir.
        </p>
      )}
    </section>
  );
}
