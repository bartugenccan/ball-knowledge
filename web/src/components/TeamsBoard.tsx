"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { clubVars } from "@/lib/clubs";
import { tone } from "@/lib/format";
import { useRowFlip } from "@/lib/useRowFlip";
import type { TeamSummary } from "@/lib/types";

const SHOW = [
  ["three_point", "Üçlük"],
  ["finishing", "Bitiricilik"],
  ["passing", "Pas"],
  ["team_defense", "Savunma"],
  ["def_rebounding", "Ribaund"],
] as const;

/** League table of teams. Choose a column and the table reshuffles. */
export function TeamsBoard({ teams, season }: { teams: TeamSummary[]; season: string }) {
  const [sort, setSort] = useState<string>("team_defense");
  const order = useMemo(() => [...teams].sort((a, b) => (b.avg[sort] ?? 0) - (a.avg[sort] ?? 0)), [teams, sort]);
  const register = useRowFlip(order.map((t) => t.code).join());

  // team averages sit in a narrow band, so colour each column by the team's standing among teams
  const relTone = useMemo(() => {
    const stats = new Map(
      SHOW.map(([k]) => {
        const vals = teams.map((t) => t.avg[k] ?? 0);
        const mean = vals.reduce((s, x) => s + x, 0) / vals.length;
        const sd = Math.sqrt(vals.reduce((s, x) => s + (x - mean) ** 2, 0) / vals.length) || 1;
        return [k, { mean, sd }] as const;
      }),
    );
    return (k: string, v: number) => {
      const s = stats.get(k as (typeof SHOW)[number][0])!;
      return tone(Math.round(11.5 + (3.2 * (v - s.mean)) / s.sd));
    };
  }, [teams]);

  return (
    <div className="relative">
      <div className="sticky top-16 z-[2] grid grid-cols-5 sm:grid-cols-[3rem_minmax(0,1fr)_repeat(5,minmax(2.6rem,5.5rem))] items-end gap-px border-b-[3px] border-ink bg-bg pb-1.5 text-[11px] font-semibold text-muted" role="group" aria-label="Sırala">
        <span className="hidden sm:col-span-2 sm:block" />
        {SHOW.map(([k, l]) => (
          <button key={k} type="button" aria-pressed={sort === k} onClick={() => setSort(k)}
            className={`truncate pb-0.5 text-center transition-colors hover:text-ink ${sort === k ? "font-extrabold text-accent-text" : ""}`}>
            {l}{sort === k && " ↓"}
          </button>
        ))}
      </div>
      <ol>
        {order.map((t, i) => (
          <li key={t.code} ref={register(t.code)} className="club border-b border-[color-mix(in_srgb,var(--ink)_14%,transparent)] bg-bg" style={clubVars(t.code)}>
            <Link href={`/teams/${t.code}?season=${season}`} prefetch={false}
              className="group grid grid-cols-5 sm:grid-cols-[3rem_minmax(0,1fr)_repeat(5,minmax(2.6rem,5.5rem))] items-center gap-px py-1.5 hover:bg-bg-2 sm:py-1">
              <span className="col-span-5 mb-1 flex min-w-0 items-baseline gap-2 sm:contents">
                <span className="num tile-r-elite grid h-7 w-8 shrink-0 place-items-center self-center text-lg sm:h-14 sm:w-10 sm:text-xl">{i + 1}</span>
                <span lang="en" className="min-w-0 pr-3">
                  <span className="display block truncate text-2xl sm:text-4xl" style={{ lineHeight: 1.05 }}>{t.name}</span>
                </span>
              </span>
              {SHOW.map(([k]) => {
                const v = t.avg[k] ?? 0;
                return (
                  <span key={k} className={`tile-${relTone(k, v)} num grid h-11 place-items-center text-sm sm:h-14 sm:text-xl`}>{v.toFixed(1)}</span>
                );
              })}
            </Link>
          </li>
        ))}
      </ol>
    </div>
  );
}
