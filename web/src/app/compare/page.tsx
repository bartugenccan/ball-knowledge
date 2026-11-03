import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { CompareBars } from "@/components/CompareBars";
import { CountUp } from "@/components/motion/CountUp";
import { Reveal } from "@/components/motion/Reveal";
import { Radar } from "@/components/Radar";
import { Skeleton } from "@/components/Skeleton";
import { getMeta, getPlayer, getPlayers } from "@/lib/api";
import { nameParts, overall, properName, radarValues, seasonLabel, tone } from "@/lib/format";
import type { PlayerDetail } from "@/lib/types";

export const metadata: Metadata = { title: "Karşılaştır" };

export default function ComparePage({ searchParams }: PageProps<"/compare">) {
  return (
    <div className="space-y-6">
      <h1 className="font-display text-5xl font-extrabold uppercase tracking-tight">Karşılaştır</h1>
      <Suspense fallback={<Skeleton className="h-[600px]" />}>
        <Compare searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function Compare({ searchParams }: { searchParams: PageProps<"/compare">["searchParams"] }) {
  const sp = await searchParams;
  const meta = await getMeta();
  const season = typeof sp.season === "string" ? sp.season : meta.latest;
  const { players } = await getPlayers({ season, sort: "minutes", limit: "400" });
  const options = [...players].sort((x, y) => properName(x.player).localeCompare(properName(y.player), "tr"));
  const a = typeof sp.a === "string" ? sp.a : players[0]?.player_id;
  const b = typeof sp.b === "string" ? sp.b : players[1]?.player_id;
  const [pa, pb] = await Promise.all([a ? getPlayer(a, season) : null, b ? getPlayer(b, season) : null]);

  return (
    <>
      <form action="/compare" className="flex flex-wrap items-end gap-3 text-sm">
        <input type="hidden" name="season" value={season} />
        {(["a", "b"] as const).map((k) => (
          <label key={k} className="flex flex-col gap-1.5">
            <span className="text-xs text-muted">{k === "a" ? "1. oyuncu" : "2. oyuncu"}</span>
            <select name={k} defaultValue={k === "a" ? a : b} className="field max-w-72 px-3 py-2">
              {options.map((p) => (
                <option key={p.player_id} value={p.player_id}>{properName(p.player)} ({p.team})</option>
              ))}
            </select>
          </label>
        ))}
        <button className="btn-accent px-4 py-2">Karşılaştır</button>
        <span className="pb-2 text-xs text-dim">{seasonLabel(season)}</span>
      </form>

      {pa && pb && (
        <>
          <Reveal>
            <section className="panel grid items-center gap-6 overflow-hidden p-6 md:grid-cols-[1fr_auto_1fr]">
              <Side d={pa} align="right" />
              <div className="grid place-items-center">
                <Radar values={radarValues(pa.ratings)} compare={radarValues(pb.ratings)} />
                <p className="mt-1 text-xs text-dim">
                  <span className="text-accent">Dolu</span>: {properName(pa.player.name)}, kesikli: {properName(pb.player.name)}
                </p>
              </div>
              <Side d={pb} align="left" />
            </section>
          </Reveal>
          <CompareBars attributes={meta.attributes} a={pa.ratings} b={pb.ratings} />
        </>
      )}
    </>
  );
}

function Side({ d, align }: { d: PlayerDetail; align: "left" | "right" }) {
  const { first, last } = nameParts(d.player.name);
  const ovr = overall(d.ratings);
  return (
    <div className={`flex flex-col gap-3 ${align === "right" ? "md:items-end md:text-right" : ""}`}>
      <Link href={`/players/${d.player.player_id}?season=${d.season}`} lang="en" className="group font-display uppercase leading-[0.9]">
        <span className="block text-lg font-semibold text-muted">{first}</span>
        <span className="block text-4xl font-extrabold transition-colors group-hover:text-accent">{last}</span>
      </Link>
      <span className="text-sm text-dim">{d.player.team_name}</span>
      <div className={`chip-${tone(ovr)} grid h-16 w-16 place-items-center rounded-2xl`}>
        <CountUp value={ovr} className="font-display text-4xl font-extrabold" />
      </div>
      <span className="text-sm text-muted">{d.per_game.pts} sayı, {d.per_game.reb} rib, {d.per_game.ast} ast</span>
    </div>
  );
}
