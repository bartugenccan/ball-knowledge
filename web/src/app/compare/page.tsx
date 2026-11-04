import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { ArenaChart } from "@/components/ArenaChart";
import { CompareBars } from "@/components/CompareBars";
import { Flap } from "@/components/motion/Flap";
import { InView } from "@/components/motion/InView";
import { Skeleton } from "@/components/Skeleton";
import { SubmitOnChange } from "@/components/SubmitOnChange";
import { getMeta, getPlayer, getPlayers } from "@/lib/api";
import { clubPair, clubVars } from "@/lib/clubs";
import { nameParts, overall, properName, radarValues, seasonLabel } from "@/lib/format";
import type { PlayerDetail } from "@/lib/types";

export const metadata: Metadata = { title: "Karşılaştır" };

export default function ComparePage({ searchParams }: PageProps<"/compare">) {
  return (
    <div className="wrap space-y-8 pt-8">
      <h1 className="display t-page stretch-in">Karşılaştır</h1>
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

  let winsA = 0;
  let winsB = 0;
  if (pa && pb) {
    const vb = new Map(pb.ratings.map((r) => [r.key, r.value]));
    for (const r of pa.ratings) {
      const y = vb.get(r.key) ?? 0;
      const other = pb.ratings.find((o) => o.key === r.key);
      // tiers and statements are not fine-grained enough to win a row
      if ((r.display ?? String(r.value)) !== String(r.value) || (other?.display ?? String(y)) !== String(y)) continue;
      if (r.value > y) winsA++;
      else if (y > r.value) winsB++;
    }
  }
  const share = winsA + winsB ? winsA / (winsA + winsB) : 0.5;

  return (
    <div className="pair space-y-8" style={pa && pb ? clubPair(pa.player.team, pb.player.team) : undefined}>
      <SubmitOnChange action="/compare" className="grid items-end gap-x-6 gap-y-3 text-sm sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
        <input type="hidden" name="season" value={season} />
        {(["a", "b"] as const).map((k) => (
          <label key={k} className="flex min-w-0 flex-col gap-1">
            <span className="text-xs font-semibold" style={{ color: k === "a" ? "var(--side-a-t, var(--ink))" : "var(--side-b-t, var(--ink))" }}>{k === "a" ? "1. oyuncu" : "2. oyuncu"}</span>
            <select name={k} defaultValue={k === "a" ? a : b} className="field w-full font-semibold">
              {options.map((p) => (
                <option key={p.player_id} value={p.player_id}>{properName(p.player)} ({p.team})</option>
              ))}
            </select>
          </label>
        ))}
        <span className="pb-2 text-xs text-muted">{seasonLabel(season)}</span>
      </SubmitOnChange>

      {pa && pb && (
        <>
          <section className="grid items-center gap-x-6 gap-y-6 md:grid-cols-[minmax(0,1fr)_minmax(0,26rem)_minmax(0,1fr)]">
            <Side d={pa} align="right" color="var(--side-a)" ink="var(--side-a-i)" text="var(--side-a-t)" />
            <InView amount={0.3} className="mx-auto w-full max-w-[26rem]">
              <ArenaChart values={radarValues(pa.ratings)} compare={radarValues(pb.ratings)} />
            </InView>
            <Side d={pb} align="left" color="var(--side-b)" ink="var(--side-b-i)" text="var(--side-b-t)" />
          </section>

          {/* tug of war: attributes won by each side pull the rope */}
          <InView amount={0.5}>
            <div className="mb-2 flex items-baseline justify-between">
              <span className="num text-5xl" style={{ color: "var(--side-a-t)" }}>{winsA}</span>
              <span className="text-xs text-muted">kazanılan özellik</span>
              <span className="num text-5xl" style={{ color: "var(--side-b-t)" }}>{winsB}</span>
            </div>
            <div className="relative h-4 overflow-hidden" style={{ background: "var(--side-b)" }} role="img" aria-label={`Kazanılan özellik: ${winsA} ve ${winsB}`}>
              <div className="tug-a absolute inset-0" style={{ background: "var(--side-a)", ["--to" as string]: share }} />
            </div>
          </InView>

          <CompareBars attributes={meta.attributes} a={pa.ratings} b={pb.ratings} />
        </>
      )}
    </div>
  );
}

function Side({ d, align, color, ink, text }: { d: PlayerDetail; align: "left" | "right"; color: string; ink: string; text: string }) {
  const { first, last } = nameParts(d.player.name);
  const ovr = overall(d.ratings);
  return (
    <div className={`club flex flex-col gap-3 ${align === "right" ? "md:items-end md:text-right" : ""}`} style={clubVars(d.player.team)}>
      <Link href={`/players/${d.player.player_id}?season=${d.season}`} lang="en" className="block min-w-0 max-w-full hover:opacity-80">
        <span className="display block text-lg text-muted">{first}</span>
        <span className="display block text-[clamp(2.4rem,4.2vw,4rem)]" style={{ color: text, overflowWrap: "anywhere" }}>{last}</span>
      </Link>
      <span className="text-sm text-muted">{d.player.team_name}</span>
      <Flap value={ovr} size="3.5rem" bg={color} ink={ink} />
      <span className="text-sm text-muted">{d.per_game.pts} sayı, {d.per_game.reb} rib, {d.per_game.ast} ast</span>
    </div>
  );
}
