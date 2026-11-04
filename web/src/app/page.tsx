import { Suspense } from "react";
import { ArenaChart } from "@/components/ArenaChart";
import { FlipLink } from "@/components/Flip";
import { LeaderIndex } from "@/components/LeaderIndex";
import { LeagueCrowd } from "@/components/LeagueCrowd";
import { Flap } from "@/components/motion/Flap";
import { InView } from "@/components/motion/InView";
import { Koreografi, type Frame } from "@/components/motion/Koreografi";
import { PlayBoard } from "@/components/PlayBoard";
import { Skeleton } from "@/components/Skeleton";
import { clubVars } from "@/lib/clubs";
import { Ticks } from "@/components/Ticks";
import { getMeta, getPlayers } from "@/lib/api";
import { nameParts, overall, overallExact, properName, radarValues, seasonLabel, tone } from "@/lib/format";
import type { AttributeMeta, PlayerRow, Rating } from "@/lib/types";
import Link from "next/link";

export default function Home() {
  return (
    <>
      <section>
        <div className="on-stand h-[30dvh] min-h-[210px] max-h-[520px] md:h-[44dvh] md:min-h-[260px]">
          <Suspense fallback={<Koreografi frames={[INTRO_FRAME]} />}>
            <HeroStand />
          </Suspense>
        </div>
        <div className="wrap grid items-end gap-x-12 gap-y-5 pt-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <h1 className="display stretch-in text-[clamp(2.8rem,6vw,5.6rem)]">
            EuroLeague&apos;i <span className="whitespace-nowrap text-accent-text">1-20</span> ölçeğinde oku.
          </h1>
          <div className="space-y-5">
            <p className="max-w-[46ch] text-lg leading-snug text-muted">
              Her oyuncunun şutu, pası, savunması ve oyun yükü, maç maç güncellenen verilerle puanlanır.
            </p>
            <div className="flex flex-wrap gap-3">
              <FlipLink href="/players">Oyuncuları incele</FlipLink>
              <FlipLink href="/coach" ghost>Set simülatörü</FlipLink>
            </div>
          </div>
        </div>
      </section>

      <section className="wrap mt-24">
        <h2 className="display t-sec mb-2">Bütün lig, tek tribünde</h2>
        <p className="mb-6 max-w-[60ch] text-muted">Her kart bir oyuncu. Özellik değiştir, tribün yeniden dizilsin. Kartın üstüne gel, kim olduğunu gör.</p>
        <Suspense fallback={<Skeleton className="h-[420px]" />}>
          <Crowd />
        </Suspense>
      </section>

      <Suspense fallback={<div className="wrap mt-24"><Skeleton className="h-[520px]" /></div>}>
        <FeaturedPlayer />
      </Suspense>

      <section className="wrap mt-24">
        <h2 className="display t-sec mb-6">Liderler</h2>
        <Suspense fallback={<Skeleton className="h-[520px]" />}>
          <Leaders />
        </Suspense>
      </section>

      <section className="mt-24 bg-board text-chalk">
        <div className="wrap grid items-center gap-x-14 gap-y-6 py-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:py-16">
          <div className="space-y-5">
            <h2 className="display t-sec">Setini çiz, 10.000 kez oynat.</h2>
            <p className="max-w-[52ch] text-chalk-2">
              Seçtiğin beşliyi rakip savunmaya karşı oynat. Hangi dalın ne sıklıkla geldiğini, şutun boş mu contest mi olacağını ve possession başına beklenen sayıyı gör.
            </p>
            <Link href="/coach" className="flip [&>.b]:bg-chalk-2 [&>.b]:text-board [&>.f]:bg-chalk [&>.f]:text-board">
              <span className="f">Koç paneline git</span>
              <span className="b" aria-hidden>Koç paneline git</span>
            </Link>
          </div>
          <PlayBoard />
        </div>
      </section>
    </>
  );
}

const ratingsOf = (p: PlayerRow, attrs: AttributeMeta[]): Rating[] =>
  attrs.map((a) => ({ key: a.key, value: Number(p[a.key]), conf: 1 }));

/** Highest overall among players with a real share of the season's games. */
async function leagueTop() {
  const meta = await getMeta();
  const { players } = await getPlayers({ sort: "minutes", limit: "400" });
  const maxGames = Math.max(...players.map((x) => x.games));
  const pool = players.filter((p) => p.games >= Math.max(3, maxGames * 0.6));
  const best = [...pool].sort((a, b) => overallExact(ratingsOf(b, meta.attributes)) - overallExact(ratingsOf(a, meta.attributes)))[0];
  return { meta, players, best };
}

const INTRO_FRAME: Frame = {
  text: "1-20",
  tone: "hot",
  caption: { kicker: "Puan ölçeği", main: "Oyuncular özellik özellik 1 ile 20 arasında puanlanır" },
};

async function HeroStand() {
  const { meta, best } = await leagueTop();
  if (!best) return <Koreografi frames={[INTRO_FRAME]} />;
  const { first, last } = nameParts(best.player);
  const ovr = overall(ratingsOf(best, meta.attributes));
  const caption = {
    kicker: `Ligin 1 numarası, ${seasonLabel(meta.latest)} genel puan sıralaması`,
    main: `${first} ${last}, ${best.team_name}: genel ${ovr}`,
    href: `/players/${best.player_id}`,
  };
  // the stand wears the colours of whoever is on top of the league
  return (
    <div className="club on-stand h-full" style={clubVars(best.team)}>
      <Koreografi
        staticFrame={2}
        frames={[
          INTRO_FRAME,
          { text: "1 NUMARA", tone: "amber", caption },
          { text: last.toLocaleUpperCase("en"), tone: "bone", caption },
          { text: String(ovr), tone: "bone", caption },
        ]}
      />
    </div>
  );
}

// Overall ratings bunch around 11-12; single attributes use the whole scale and make a better crowd.
const CROWD_KEYS = ["three_point", "finishing", "passing", "def_rebounding", "shot_blocking", "steals"];

async function Crowd() {
  const { meta, players } = await leagueTop();
  const attrs = CROWD_KEYS.flatMap((key) => meta.attributes.filter((a) => a.key === key).map((a) => ({ key, label: a.label })));
  return (
    <LeagueCrowd
      attrs={attrs}
      players={players.map((p) => ({
        id: p.player_id,
        name: properName(p.player),
        team: p.team,
        vals: Object.fromEntries(CROWD_KEYS.map((k) => [k, Number(p[k])])),
      }))}
    />
  );
}

async function FeaturedPlayer() {
  const { meta, best } = await leagueTop();
  if (!best) return null;
  const ratings = ratingsOf(best, meta.attributes);
  const ovr = overall(ratings);
  const { first, last } = nameParts(best.player);
  const top = meta.attributes
    .filter((a) => !best.labels[a.key])
    .sort((a, b) => Number(best[b.key]) - Number(best[a.key]))
    .slice(0, 4);
  return (
    <section className="club on-stand mt-24" style={clubVars(best.team)}>
      <div className="wrap grid items-center gap-x-12 gap-y-6 py-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] lg:py-14">
        <InView amount={0.3} className="order-2 mx-auto w-full max-w-[520px] lg:order-1">
          <ArenaChart values={radarValues(ratings)} center={ovr} />
        </InView>
        <div className="order-1 space-y-6 lg:order-2">
          <div>
            <p className="mb-2 text-sm text-muted">Ligin en yüksek genel puanı, {seasonLabel(meta.latest)}</p>
            <Link href={`/players/${best.player_id}`} lang="en" className="group block">
              <span className="display block text-2xl text-muted">{first}</span>
              <span className="display t-fit block transition-colors group-hover:text-accent-text" style={{ ["--len" as string]: Math.max(last.length, 7), fontSize: `min(calc(46vw / (${Math.max(last.length, 7)} * 0.52)), 8.5rem)` }}>{last}</span>
            </Link>
            <p className="mt-2 text-sm text-muted">{best.team_name}</p>
          </div>
          <div className="flex items-center gap-6">
            <Flap value={ovr} size="5rem" bg="var(--ink)" ink="var(--bg)" />
            <ul className="grid flex-1 gap-3 sm:grid-cols-2">
              {top.map((a, i) => (
                <li key={a.key}>
                  <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
                    <span className="truncate">{a.label}</span>
                    <span className={`num text-lg ${tone(Number(best[a.key]))}`}>{Number(best[a.key])}</span>
                  </div>
                  <InView amount={0}><Ticks value={Number(best[a.key])} row={i * 2} /></InView>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

const LEADER_KEYS = ["three_point", "passing", "rim_protection", "steals", "finishing", "shot_creation"];

async function Leaders() {
  const meta = await getMeta();
  // rated_only: too little data means no place on a leader list, so a list can be empty early in a season
  const lists = await Promise.all(LEADER_KEYS.map((key) => getPlayers({ sort: key, limit: "5", rated_only: "true" })));
  const attr = new Map(meta.attributes.map((a) => [a.key, a]));
  return (
    <LeaderIndex
      lists={LEADER_KEYS.map((key, i) => ({
        key,
        label: attr.get(key)?.label ?? key,
        players: lists[i].players.map((p) => ({ id: p.player_id, name: properName(p.player), team: p.team, value: Number(p[key]) })),
      })).filter((list) => list.players.length > 0)}
    />
  );
}
