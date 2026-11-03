import Link from "next/link";
import { Suspense } from "react";
import { LeaderBars } from "@/components/LeaderBars";
import { CountUp } from "@/components/motion/CountUp";
import { Reveal, Stagger, StaggerItem } from "@/components/motion/Reveal";
import { Spotlight } from "@/components/motion/Spotlight";
import { Radar } from "@/components/Radar";
import { Skeleton } from "@/components/Skeleton";
import { getMeta, getPlayers } from "@/lib/api";
import { nameParts, overall, properName, radarValues, seasonLabel, tone } from "@/lib/format";
import type { AttributeMeta, PlayerRow, Rating } from "@/lib/types";

export default function Home() {
  return (
    <div className="space-y-16">
      <section className="grid items-center gap-10 pt-4 lg:grid-cols-[1.05fr_1fr]">
        <div className="space-y-6">
          <h1 className="font-display text-5xl font-extrabold uppercase leading-[0.95] tracking-tight md:text-7xl">
            EuroLeague&apos;i <span className="text-accent">1–20</span> ölçeğinde oku.
          </h1>
          <p className="max-w-[46ch] text-lg leading-relaxed text-muted">
            Her oyuncunun şut, pas, savunma ve baskı altındaki performansı, maç maç güncellenen verilerle puanlanır.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/players" className="btn-accent px-5 py-2.5">Oyuncuları incele</Link>
            <Link href="/coach" className="btn-ghost px-5 py-2.5">Set simülatörü</Link>
          </div>
        </div>
        <Suspense fallback={<Skeleton className="h-[420px]" />}>
          <FeaturedPlayer />
        </Suspense>
      </section>

      <Suspense fallback={<Skeleton className="h-[520px]" />}>
        <Leaders />
      </Suspense>

      <Reveal>
        <section className="panel grid items-center gap-6 overflow-hidden p-6 md:grid-cols-[1fr_auto] md:p-8">
          <div aria-hidden className="pointer-events-none absolute -bottom-32 left-1/3 h-72 w-72 rounded-full bg-accent/15 blur-3xl" />
          <div className="relative space-y-2">
            <h2 className="font-display text-3xl font-bold uppercase">Setini çiz, 10.000 kez oynat.</h2>
            <p className="max-w-[60ch] text-muted">
              Koç paneli, seçtiğin beşliyi rakip savunmaya karşı oynatır. Hangi dalın ne sıklıkla geldiğini, şutun boş mu contest mi
              olacağını ve possession başına beklenen sayıyı gösterir.
            </p>
          </div>
          <Link href="/coach" className="btn-accent relative px-5 py-2.5 text-center">Koç paneline git</Link>
        </section>
      </Reveal>
    </div>
  );
}

const ratingsOf = (p: PlayerRow, attrs: AttributeMeta[]): Rating[] =>
  attrs.map((a) => ({ key: a.key, value: Number(p[a.key]), conf: 1 }));

async function FeaturedPlayer() {
  const meta = await getMeta();
  const { players } = await getPlayers({ sort: "minutes", limit: "400" });
  const pool = players.filter((p) => p.games >= Math.max(3, Math.max(...players.map((x) => x.games)) * 0.6));
  const best = [...pool].sort((a, b) => overall(ratingsOf(b, meta.attributes)) - overall(ratingsOf(a, meta.attributes)))[0];
  if (!best) return null;
  const ratings = ratingsOf(best, meta.attributes);
  const ovr = overall(ratings);
  const { first, last } = nameParts(best.player);
  const top = [...meta.attributes].sort((a, b) => Number(best[b.key]) - Number(best[a.key])).slice(0, 3);
  return (
    <div className="rise" style={{ ["--i" as string]: 4 }}>
      <Spotlight className="overflow-hidden p-6">
        <div aria-hidden className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-accent/25 blur-3xl" />
        <div className="relative flex items-start justify-between gap-4">
          <div>
            <p className="text-sm text-muted">Ligin en yüksek genel puanı · {seasonLabel(meta.latest)}</p>
            <Link href={`/players/${best.player_id}`} lang="en" className="group mt-1 block font-display uppercase leading-[0.9]">
              <span className="block text-xl font-semibold text-muted">{first}</span>
              <span className="block text-5xl font-extrabold transition-colors group-hover:text-accent">{last}</span>
            </Link>
            <p className="mt-1 text-sm text-dim">{best.team_name}</p>
          </div>
          <div className={`chip-${tone(ovr)} grid h-20 w-20 shrink-0 place-items-center rounded-2xl`}>
            <CountUp value={ovr} className="font-display text-5xl font-extrabold leading-none" />
          </div>
        </div>
        <div className="relative mt-2 grid items-center gap-4 sm:grid-cols-[1fr_auto]">
          <Radar values={radarValues(ratings)} size={260} />
          <ul className="space-y-3">
            {top.map((a) => (
              <li key={a.key} className="flex items-center justify-between gap-6">
                <span className="text-sm text-muted">{a.label}</span>
                <span className={`font-display text-3xl font-bold ${tone(Number(best[a.key]))}`}>{best[a.key]}</span>
              </li>
            ))}
          </ul>
        </div>
      </Spotlight>
    </div>
  );
}

// 3-column bento: one 2x2 feature cell, two stacked cells beside it, three cells below (6 items, 9 slots).
const LEADER_CELLS: { key: string; span: string }[] = [
  { key: "three_point", span: "sm:col-span-2 lg:row-span-2" },
  { key: "passing", span: "" },
  { key: "rim_protection", span: "" },
  { key: "clutch", span: "" },
  { key: "finishing", span: "" },
  { key: "shot_creation", span: "" },
];

async function Leaders() {
  const meta = await getMeta();
  const lists = await Promise.all(LEADER_CELLS.map((c) => getPlayers({ sort: c.key, limit: "5" })));
  const attr = new Map(meta.attributes.map((a) => [a.key, a]));
  return (
    <section className="space-y-5">
      <Reveal>
        <h2 className="font-display text-3xl font-bold uppercase tracking-wide">Liderler</h2>
      </Reveal>
      <Stagger className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {LEADER_CELLS.map((cell, i) => {
          const a = attr.get(cell.key)!;
          const [lead, ...rest] = lists[i].players;
          const big = i === 0;
          return (
            <StaggerItem key={cell.key} className={cell.span}>
              <Spotlight className={`flex h-full flex-col p-5 ${big ? "bg-[radial-gradient(500px_300px_at_100%_0%,rgb(240_122_43/0.18),transparent_70%)]" : ""}`}>
                <h3 className="text-sm text-muted">{a.label}</h3>
                {lead && (
                  <Link href={`/players/${lead.player_id}`} className="group mt-2 flex items-end justify-between gap-3">
                    <span lang="en" className={`font-display font-bold uppercase leading-none transition-colors group-hover:text-accent ${big ? "text-5xl" : "text-2xl"}`}>
                      {properName(lead.player)}
                    </span>
                    <span className={`font-display font-extrabold leading-none ${tone(Number(lead[cell.key]))} ${big ? "text-7xl" : "text-4xl"}`}>
                      {lead[cell.key]}
                    </span>
                  </Link>
                )}
                {lead && <p className="mt-1 text-xs text-dim">{lead.team_name}</p>}
                {big && <LeaderBars players={lists[i].players} attrKey={cell.key} />}
                <ol className={`mt-auto space-y-1.5 pt-4 text-sm ${big ? "hidden" : "hidden sm:block"}`}>
                  {rest.map((p) => (
                    <li key={p.player_id} className="flex items-center gap-2">
                      <Link href={`/players/${p.player_id}`} className="flex-1 truncate text-muted hover:text-ink">
                        {properName(p.player)}
                      </Link>
                      <span className="text-xs text-dim">{p.team}</span>
                      <span className={`w-6 text-right font-display text-lg font-bold ${tone(Number(p[cell.key]))}`}>{p[cell.key]}</span>
                    </li>
                  ))}
                </ol>
              </Spotlight>
            </StaggerItem>
          );
        })}
      </Stagger>
    </section>
  );
}
