import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { ArenaChart } from "@/components/ArenaChart";
import { FlipLink } from "@/components/Flip";
import { FormSkyline } from "@/components/FormSkyline";
import { Flap } from "@/components/motion/Flap";
import { InView } from "@/components/motion/InView";
import { Odo } from "@/components/motion/Odo";
import { RatingsWindow } from "@/components/RatingsWindow";
import { ShotChart } from "@/components/ShotChart";
import { PlayerSkeleton } from "@/components/Skeleton";
import { getMeta, getPlayer } from "@/lib/api";
import { clubVars } from "@/lib/clubs";
import { gameTone, nameParts, overall, pct, properName, radarValues, seasonLabel, ZONE_LABEL } from "@/lib/format";

export async function generateMetadata({ params, searchParams }: PageProps<"/players/[id]">): Promise<Metadata> {
  const { id } = await params;
  const sp = await searchParams;
  const d = await getPlayer(id, typeof sp.season === "string" ? sp.season : undefined);
  return { title: `${properName(d.player.name)}, ${seasonLabel(d.season)}` };
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
    { label: "Sayı", value: d.per_game.pts },
    { label: "Ribaund", value: d.per_game.reb },
    { label: "Asist", value: d.per_game.ast },
    { label: "PIR", value: d.per_game.pir },
    { label: "Dakika", value: p.mpg },
  ];

  return (
    <div className="club" style={clubVars(p.team)}>
      <section className="on-stand overflow-hidden">
        <div className="wrap grid items-center gap-x-10 gap-y-6 pb-8 pt-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,27rem)]">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1">
              <Link href={`/teams/${p.team}?season=${d.season}`} className="font-semibold underline underline-offset-4 hover:text-accent-text">{p.team_name}</Link>
              <div className="flex flex-wrap gap-x-4" role="tablist" aria-label="Sezon">
                {d.seasons.map((s) => (
                  <Link key={s} href={`/players/${p.player_id}?season=${s}`} role="tab" aria-selected={s === d.season} className="tab">{seasonLabel(s)}</Link>
                ))}
              </div>
            </div>
            <h1 lang="en" className="mt-6">
              <span className="display block text-2xl text-muted md:text-3xl">{first}</span>
              <span className="display t-fit stretch-in block" style={{ ["--len" as string]: Math.max(last.length, 6) }}>{last}</span>
            </h1>
            <div className="mt-8 flex flex-wrap items-end gap-x-10 gap-y-6">
              <div className="flex items-end gap-3">
                <Flap value={ovr} size="clamp(4.5rem, 8vw, 6.5rem)" bg="var(--ink)" ink="var(--bg)" />
                <span className="pb-1 text-xs text-muted">genel<br />{p.games} maç</span>
              </div>
              <div className="min-w-0 basis-full space-y-4 sm:basis-0 sm:flex-1">
                <dl className="grid grid-cols-3 gap-x-5 gap-y-4 sm:grid-cols-5">
                  {stats.map((s) => (
                    <div key={s.label}>
                      <dt className="text-xs text-muted">{s.label}</dt>
                      <dd className="num text-3xl"><Odo value={s.value} decimals={1} /></dd>
                    </div>
                  ))}
                </dl>
                <FlipLink href={`/compare?a=${p.player_id}&season=${d.season}`}>Karşılaştır</FlipLink>
              </div>
            </div>
          </div>
          <InView amount={0.3} className="mx-auto w-full max-w-[27rem]">
            <ArenaChart values={radarValues(d.ratings)} />
          </InView>
          {!p.qualified && (
            <p className="border-t border-[var(--line)] pt-3 text-sm text-muted lg:col-span-2">
              Bu sezon az süre aldı. Puanlar lig ortalamasına güçlü şekilde çekildi, güven düşük.
            </p>
          )}
        </div>
      </section>

      <div className="wrap space-y-20 pt-14">
        <RatingsWindow attributes={meta.attributes} season={d.ratings} months={d.months} />

        <div className="grid gap-x-12 gap-y-14 lg:grid-cols-[1.1fr_1fr]">
          <section className="min-w-0 space-y-6">
            <h2 className="display t-sec">Form</h2>
            <FormSkyline games={d.games} />
            <div className="overflow-x-auto">
              <table className="ledger w-full text-sm">
                <thead>
                  <tr className="text-left">
                    <th className="py-2 pr-2">TUR</th>
                    <th className="px-2 py-2">RAKİP</th>
                    <th className="px-2 py-2 text-right">DK</th>
                    <th className="px-2 py-2 text-right">SAYI</th>
                    <th className="px-2 py-2 text-right">RİB</th>
                    <th className="px-2 py-2 text-right">AST</th>
                    <th className="px-2 py-2 text-right">PIR</th>
                    <th className="py-2 pl-2 text-right">PUAN</th>
                  </tr>
                </thead>
                <tbody>
                  {recent.map((g) => (
                    <tr key={g.gamecode}>
                      <td className="py-1.5 pr-2 text-dim">{g.round ?? "-"}</td>
                      <td className="px-2 py-1.5"><span className="text-dim">{g.is_home ? "vs" : "@"}</span> {g.opponent}</td>
                      <td className="px-2 py-1.5 text-right">{g.minutes.toFixed(0)}</td>
                      <td className="px-2 py-1.5 text-right font-semibold">{g.pts}</td>
                      <td className="px-2 py-1.5 text-right">{g.orb + g.drb}</td>
                      <td className="px-2 py-1.5 text-right">{g.ast}</td>
                      <td className="px-2 py-1.5 text-right">{g.pir}</td>
                      <td className="py-1 pl-2 text-right">
                        <span
                          className={`tile-${gameTone(g.game_rating)} num inline-grid h-7 w-10 place-items-center text-sm ${g.short_game ? "opacity-50" : ""}`}
                          title={g.short_game ? "10 dakikadan az süre: puan az şey söyler" : undefined}
                        >
                          {g.game_rating.toFixed(1)}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="min-w-0 space-y-6">
            <h2 className="display t-sec">Şut haritası</h2>
            <ShotChart shots={d.shots} />
            <div className="grid grid-cols-3 gap-x-4 gap-y-4">
              {Object.entries(d.shooting).map(([z, v]) => (
                <div key={z}>
                  <div className="text-xs text-muted">{ZONE_LABEL[z] ?? z}</div>
                  <div className="num text-2xl md:text-3xl"><Odo value={100 * v} decimals={1} suffix="%" /></div>
                </div>
              ))}
            </div>
            <p className="text-xs text-dim">
              Bölge yüzdeleri küçük örneklem düzeltmesinden geçmiş, ligin seviyesine göre beklenen değerlerdir. Pota altı ile boyalı alan
              ayrımı salondan salona farklı işaretlendiği için birlikte verilir.
            </p>
            <dl className="grid gap-x-6 gap-y-3 border-t border-[var(--line)] pt-4 text-sm sm:grid-cols-[auto_1fr]">
              <dt className="font-semibold text-ink">Üçlük kullanımı</dt>
              <dd className="text-muted">Maç başı {d.per_game.fg3m} isabet, {d.per_game.fg3a} deneme. Köşeden {d.info.corner3_attempts} deneme.</dd>
              <dt className="font-semibold text-ink">Bu sezon clutch</dt>
              <dd className="text-muted">
                {d.info.clutch.per_play === null
                  ? "Bu sezon clutch hücumu yok."
                  : `${d.info.clutch.points} sayı, ${d.info.clutch.plays} hücum (hücum başına ${d.info.clutch.per_play}).`}{" "}
                Son 5 dakika, fark en fazla 5. Olanı anlatır; verimiz kalıcı bir clutch becerisi göstermediği için puan değildir.
              </dd>
              {d.info.inside_on_off.fga_on !== null && d.info.inside_on_off.pct_on !== null && d.info.inside_on_off.pct_off !== null && (
                <>
                  <dt className="font-semibold text-ink">Sahadayken rakip</dt>
                  <dd className="text-muted">
                    100 hücumda {d.info.inside_on_off.fga_on} boyalı alan denemesi (kenardayken {d.info.inside_on_off.fga_off}), isabet{" "}
                    {pct(d.info.inside_on_off.pct_on)} (kenardayken {pct(d.info.inside_on_off.pct_off)}). Takım arkadaşlarından ayrılmamış ham sayılar.
                  </dd>
                </>
              )}
            </dl>
          </section>
        </div>
      </div>
    </div>
  );
}
