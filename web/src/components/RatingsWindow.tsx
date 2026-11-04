"use client";

import { useState } from "react";
import { AttributeCard } from "@/components/AttributeCard";
import { monthLabel } from "@/lib/format";
import type { AttributeMeta, Rating } from "@/lib/types";

/** Season vs. monthly view of the attributes. Switching month re-lights the lamps in place. */
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
    <section className="space-y-6">
      <h2 className="display t-sec">Özellikler</h2>
      <div className="flex flex-wrap gap-x-5 gap-y-1" role="tablist" aria-label="Dönem">
        {tabs.map((t) => (
          <button key={t.id} type="button" role="tab" aria-selected={win === t.id} onClick={() => setWin(t.id)} className="tab">
            {t.label}
            {t.games !== undefined && <span className="ml-1.5 text-xs font-medium opacity-70">{t.games} maç</span>}
          </button>
        ))}
      </div>
      <AttributeCard attributes={attributes} ratings={month ? month.ratings : season} compare={month ? season : undefined} />
      {month && (
        <p className="text-xs text-dim">
          Aylık puan formu gösterir: o ayın verisi, oyuncunun o aydan önceki seviyesine doğru çekilir. Ölçek sezonla aynı. Küçük sayı sezona göre farkı gösterir.
        </p>
      )}
    </section>
  );
}
