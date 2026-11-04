import type { Metadata } from "next";
import { Suspense } from "react";
import { PlayersBoard } from "@/components/PlayersBoard";
import { Skeleton } from "@/components/Skeleton";
import { SubmitOnChange } from "@/components/SubmitOnChange";
import { getMeta, getPlayers } from "@/lib/api";
import { overall, properName, seasonLabel, shortLabel } from "@/lib/format";
import type { Group } from "@/lib/types";

export const metadata: Metadata = { title: "Oyuncular" };

type SP = Promise<Record<string, string | string[] | undefined>>;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

export default function PlayersPage({ searchParams }: { searchParams: SP }) {
  return (
    <div className="wrap space-y-6 pt-8">
      <h1 className="display t-page stretch-in">Oyuncular</h1>
      <Suspense fallback={<Skeleton className="h-[600px]" />}>
        <PlayersTable searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function PlayersTable({ searchParams }: { searchParams: SP }) {
  const sp = await searchParams;
  const meta = await getMeta();
  const season = one(sp.season) ?? meta.latest;
  const { players } = await getPlayers({ season, sort: "minutes", limit: "400" });
  const rows = players.map((p) => {
    const vals = Object.fromEntries(meta.attributes.map((a) => [a.key, Number(p[a.key])]));
    const ovr = overall(meta.attributes.map((a) => ({ key: a.key, value: vals[a.key], conf: 1 })));
    // a statement ("Üçlük kullanmıyor") has no value to rank by: it sorts below every number
    for (const [k, label] of Object.entries(p.labels)) {
      if (shortLabel(label) === "–") vals[k] = -1;
    }
    return {
      id: p.player_id,
      name: properName(p.player),
      team: p.team,
      games: p.games,
      mpg: Number(p.mpg),
      ovr,
      vals,
      labels: p.labels,
    };
  });

  return (
    <>
      <SubmitOnChange action="/players" className="flex items-center gap-3 text-sm">
        <label htmlFor="season" className="text-muted">Sezon</label>
        <select id="season" name="season" defaultValue={season} className="field font-semibold">
          {meta.seasons.map((s) => <option key={s} value={s}>{seasonLabel(s)}</option>)}
        </select>
        <noscript><button className="underline">Uygula</button></noscript>
      </SubmitOnChange>
      {/* season changes reload the rows; key resets sort state only when the data really differs */}
      <PlayersBoard
        key={season}
        rows={rows}
        attributes={meta.attributes}
        season={season}
        initial={{ group: (one(sp.group) as Group) ?? "hucum", sort: one(sp.sort) ?? "ovr", q: one(sp.q) ?? "" }}
      />
    </>
  );
}
