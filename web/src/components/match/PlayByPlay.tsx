"use client";

import { useState } from "react";
import type { GameEvent } from "@/lib/match";

type Filter = "key" | "score" | "all";
const FILTERS: { key: Filter; label: string }[] = [
  { key: "key", label: "Önemli anlar" },
  { key: "score", label: "Sayılar" },
  { key: "all", label: "Her şey" },
];
const SKIP_IN_ALL = new Set(["period_end"]);

function scored(e: GameEvent) {
  return e.event === "make" || (e.event === "ft" && !/ 0\/\d$/.test(e.text));
}

function keep(e: GameEvent, f: Filter) {
  if (e.event === "period_start") return true;
  if (f === "all") return !SKIP_IN_ALL.has(e.event);
  if (f === "score") return scored(e);
  // made threes, what the ratings single out, timeouts and subs forced by fouls
  return (e.event === "make" && (e.value === 3 || Boolean(e.note))) || Boolean(e.note) || e.event === "timeout"
    || e.text.includes("faul sıkıntısı") || e.text.includes("oyun dışı") || e.text.startsWith("Mola");
}

function Row({ e, home }: { e: GameEvent; home: string }) {
  const hit = scored(e);
  const side = e.team === home ? "var(--side-a-t)" : "var(--side-b-t)";
  if (e.event === "period_start") {
    return (
      <li className="mt-2 border-b-2 border-ink py-1 first:mt-0">
        <span className="font-semibold">{e.text}</span>
        {e.starters && e.period === 1 && (
          <div className="mt-1 space-y-0.5 text-xs text-muted">
            {Object.entries(e.starters).map(([code, names]) => <p key={code} lang="en"><span className="font-semibold">{code}:</span> {names.join(", ")}</p>)}
          </div>
        )}
      </li>
    );
  }
  return (
    <li className={`grid grid-cols-[2.6rem_2.6rem_1fr_auto] items-baseline gap-x-2 border-b border-line py-1 text-sm ${hit ? "" : "text-muted"}`}>
      <span className="num text-xs text-dim">{e.clock}</span>
      <span className="text-xs font-bold" style={e.team ? { color: side } : undefined}>{e.team ?? ""}</span>
      <span lang="en" className={hit ? "font-semibold" : ""}>
        {e.text}
        {e.note && <span lang="tr" className="ml-2 whitespace-nowrap rounded-sm bg-bg-2 px-1.5 py-px text-xs font-medium text-muted">{e.note}</span>}
      </span>
      <span className={`num text-right text-xs ${hit ? "text-ink" : "text-dim"}`}>{e.home}-{e.away}</span>
    </li>
  );
}

/** One game's events, grouped by period, with a filter so a reader can skim or go through all of it. */
export function PlayByPlay({ events, home, period }: { events: GameEvent[]; home: string; period?: number }) {
  const [filter, setFilter] = useState<Filter>("key");
  const shown = events.filter((e) => keep(e, filter) && (period === undefined || e.period === period));
  return (
    <div>
      <div className="mb-2 flex gap-4" role="tablist" aria-label="Olay filtresi">
        {FILTERS.map((f) => (
          <button key={f.key} type="button" role="tab" aria-selected={filter === f.key} className="tab !text-sm" onClick={() => setFilter(f.key)}>{f.label}</button>
        ))}
      </div>
      <ol className="max-h-[560px] overflow-y-auto pr-1">
        {shown.map((e, i) => <Row key={`${e.elapsed}-${i}`} e={e} home={home} />)}
      </ol>
    </div>
  );
}

/** The real game and a scenario next to each other, period by period. */
export function SideBySide({ left, right, leftLabel, rightLabel, home }: {
  left: GameEvent[]; right: GameEvent[]; leftLabel: string; rightLabel: string; home: string;
}) {
  const [period, setPeriod] = useState(1);
  const periods = [...new Set([...left, ...right].map((e) => e.period))].sort((a, b) => a - b);
  const [filter, setFilter] = useState<Filter>("score");
  const pick = (list: GameEvent[]) => list.filter((e) => e.period === period && keep(e, filter));
  const end = (list: GameEvent[]) => {
    const part = list.filter((e) => e.period === period);
    const last = part[part.length - 1];
    return last ? `${last.home}-${last.away}` : "–";
  };
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-4" role="tablist" aria-label="Çeyrek">
          {periods.map((p) => (
            <button key={p} type="button" role="tab" aria-selected={period === p} className="tab !text-sm" onClick={() => setPeriod(p)}>
              {p <= 4 ? `${p}. çeyrek` : `${p - 4}. uzatma`}
            </button>
          ))}
        </div>
        <div className="flex gap-4" role="tablist" aria-label="Olay filtresi">
          {FILTERS.map((f) => (
            <button key={f.key} type="button" role="tab" aria-selected={filter === f.key} className="tab !text-sm" onClick={() => setFilter(f.key)}>{f.label}</button>
          ))}
        </div>
      </div>
      <div className="grid gap-x-8 gap-y-6 lg:grid-cols-2">
        {[{ label: leftLabel, list: left }, { label: rightLabel, list: right }].map((c) => (
          <div key={c.label}>
            <p className="mb-1 flex items-baseline justify-between font-semibold">
              {c.label}
              <span className="num text-sm text-muted">Çeyrek sonu {end(c.list)}</span>
            </p>
            <ol className="max-h-[520px] overflow-y-auto pr-1">
              {pick(c.list).map((e, i) => <Row key={`${e.elapsed}-${i}`} e={e} home={home} />)}
            </ol>
          </div>
        ))}
      </div>
    </div>
  );
}
