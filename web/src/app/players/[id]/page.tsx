import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { FormChart } from "@/components/FormChart";
import { CountUp } from "@/components/motion/CountUp";
import { Reveal } from "@/components/motion/Reveal";
import { Radar } from "@/components/Radar";
import { RatingsWindow } from "@/components/RatingsWindow";
import { ShotChart } from "@/components/ShotChart";
import { PlayerSkeleton } from "@/components/Skeleton";
import { getMeta, getPlayer } from "@/lib/api";
import { gameTone, nameParts, overall, properName, radarValues, seasonLabel, tone, ZONE_LABEL } from "@/lib/format";

export async function generateMetadata({ params, searchParams }: PageProps<"/players/[id]">): Promise<Metadata> {
  const { id } = await params;
  const sp = await searchParams;
  const d = await getPlayer(id, typeof sp.season === "string" ? sp.season : undefined);
  return { title: `${properName(d.player.name)} · ${seasonLabel(d.season)}` };
}

export default function PlayerPage(props: PageProps<"/players/[id]">) {
  return (
    <Suspense fallback={<PlayerSkeleton />}>
      <PlayerContent {...props} />
    </Suspense>
  );
}

async function PlayerContent({ params, searchParams }: PageProps<"/players/[id]">) {
  const { id } = await params;
  const sp = await searchParams;
  const season = typeof sp.season === "string" ? sp.season : undefined;
  const [meta, d] = await Promise.all([getMeta(), getPlayer(id, season)]);
  const p = d.player;
  const { first, last } = nameParts(p.name);
  const ovr = overall(d.ratings);
  const recent = [...d.games].reverse().slice(0, 10);
  const stats = [
    { label: "Sayı", value: d.per_game.pts, dec: 1 },
    { label: "Ribaund", value: d.per_game.reb, dec: 1 },
    { label: "Asist", value: d.per_game.ast, dec: 1 },
    { label: "PIR", value: d.per_game.pir, dec: 1 },
    { label: "Dakika", value: p.mpg, dec: 1 },
  ];

  return (
    <div className="space-y-10">
      {/* hero */}
      <section className="panel overflow-hidden">
        <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-accent/20 blur-3xl" />
        <div className="relative grid gap-6 p-6 md:grid-cols-[1fr_auto] md:p-8">
          <div className="flex flex-col justify-between gap-6">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <Link href={`/teams/${p.team}?season=${d.season}`} className="btn-ghost px-3 py-1 text-muted hover:text-ink">
                {p.team_name}
              </Link>
              {d.seasons.map((s) => (
                <Link key={s} href={`/players/${p.player_id}?season=${s}`}
                  className={`pill px-3 py-1 ${s === d.season ? "bg-ink text-bg" : "text-muted hover:bg-panel-2 hover:text-ink"}`}>
                  {seasonLabel(s)}
                </Link>
              ))}
            </div>
            <div className="flex items-end gap-5">
              <div className={`chip-${tone(ovr)} grid h-24 w-24 shrink-0 place-items-center rounded-2xl ring-1 ring-white/10`}>
                <CountUp value={ovr} className="font-display text-6xl font-extrabold leading-none" />
                <span className="-mt-3 text-[10px] uppercase tracking-widest opacity-80">genel</span>
              </div>
              <h1 lang="en" className="font-display uppercase leading-[0.9]">
                <span className="block text-2xl font-semibold text-muted md:text-3xl">{first}</span>
                <span className="block text-5xl font-extrabold tracking-tight md:text-7xl">{last}</span>
              </h1>
            </div>
            <dl className="grid grid-cols-3 gap-4 sm:grid-cols-5">
              {stats.map((s) => (
                <div key={s.label}>
                  <dt className="text-xs text-dim">{s.label}</dt>
                  <dd className="font-display text-3xl font-bold"><CountUp value={s.value} decimals={s.dec} /></dd>
                </div>
              ))}
            </dl>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <Link href={`/compare?a=${p.player_id}&season=${d.season}`} className="btn-accent px-4 py-2">Karşılaştır</Link>
              <span className="text-dim">{p.games} maç</span>
            </div>
          </div>
          <div className="grid place-items-center">
            <Radar values={radarValues(d.ratings)} />
          </div>
        </div>
        {!p.qualified && (
          <p className="border-t border-line bg-bg-2/60 px-6 py-2.5 text-sm text-muted">
            Bu sezon az süre aldı. Puanlar lig ortalamasına güçlü şekilde çekildi, güven düşük.
          </p>
        )}
      </section>

      <RatingsWindow attributes={meta.attributes} season={d.ratings} months={d.months} />

      <div className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
        <Reveal className="space-y-3">
          <h2 className="font-display text-2xl font-bold uppercase tracking-wide">Form</h2>
          <div className="panel p-4">
            <FormChart games={d.games} />
          </div>
          <div className="panel overflow-x-auto">
            <table className="data-table w-full text-sm">
              <thead>
                <tr className="text-left">
                  <th className="px-4 py-2.5">TUR</th>
                  <th className="px-2 py-2.5">RAKİP</th>
                  <th className="px-2 py-2.5 text-right">DK</th>
                  <th className="px-2 py-2.5 text-right">SAYI</th>
                  <th className="px-2 py-2.5 text-right">RİB</th>
                  <th className="px-2 py-2.5 text-right">AST</th>
                  <th className="px-2 py-2.5 text-right">PIR</th>
                  <th className="px-4 py-2.5 text-right">PUAN</th>
                </tr>
              </thead>
              <tbody>
                {recent.map((g, i) => (
                  <tr key={g.gamecode} className="rise border-t border-line/60" style={{ ["--i" as string]: i }}>
                    <td className="px-4 py-2 text-dim">{g.round ?? "-"}</td>
                    <td className="px-2 py-2">
                      <span className="text-dim">{g.is_home ? "vs" : "@"}</span> {g.opponent}
                    </td>
                    <td className="px-2 py-2 text-right">{g.minutes.toFixed(0)}</td>
                    <td className="px-2 py-2 text-right font-semibold">{g.pts}</td>
                    <td className="px-2 py-2 text-right">{g.orb + g.drb}</td>
                    <td className="px-2 py-2 text-right">{g.ast}</td>
                    <td className="px-2 py-2 text-right">{g.pir}</td>
                    <td className="px-4 py-2 text-right">
                      <span className={`chip-${gameTone(g.game_rating)} rounded-md px-2 py-0.5 font-mono text-xs font-semibold`}>
                        {g.game_rating.toFixed(1)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>
        <Reveal className="space-y-3" delay={0.1}>
          <h2 className="font-display text-2xl font-bold uppercase tracking-wide">Şut haritası</h2>
          <ShotChart shots={d.shots} />
          <div className="panel grid grid-cols-3 gap-x-4 gap-y-3 p-4">
            {Object.entries(d.shooting).map(([z, v]) => (
              <div key={z}>
                <div className="text-xs text-dim">{ZONE_LABEL[z] ?? z}</div>
                <div className="font-display text-2xl font-bold">
                  <CountUp value={100 * v} decimals={1} suffix="%" />
                </div>
              </div>
            ))}
          </div>
          <p className="text-xs text-dim">Bölge yüzdeleri küçük örneklem düzeltmesinden geçmiş beklenen değerlerdir.</p>
        </Reveal>
      </div>
    </div>
  );
}
