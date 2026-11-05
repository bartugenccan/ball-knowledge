import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Skeleton } from "@/components/Skeleton";
import { getMeta, getStandings } from "@/lib/api";
import { clubVars } from "@/lib/clubs";
import { seasonLabel } from "@/lib/format";
import type { StandingRow } from "@/lib/match";

export const metadata: Metadata = { title: "Puan Durumu" };

export default function StandingsPage({ searchParams }: PageProps<"/standings">) {
  return (
    <div className="wrap space-y-5 pt-8">
      <h1 className="display t-page stretch-in">Puan Durumu</h1>
      <Suspense fallback={<Skeleton className="h-[640px]" />}>
        <Table searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

function Form({ results }: { results: boolean[] }) {
  return (
    <span className="inline-flex gap-1" role="img" aria-label={`Son ${results.length} maç: ${results.map((w) => (w ? "galibiyet" : "mağlubiyet")).join(", ")}`}>
      {results.map((won, i) => (
        <span key={i} className={`size-2.5 rounded-full ${won ? "bg-ink" : "bg-line"}`} title={won ? "Galibiyet" : "Mağlubiyet"} />
      ))}
    </span>
  );
}

function Row({ r, season, divider }: { r: StandingRow; season: string; divider: boolean }) {
  return (
    <tr className={`club border-b border-line ${divider ? "border-b-2 border-b-ink" : ""}`} style={clubVars(r.code)}>
      <td className="num w-8 py-2 pr-2 text-right text-muted">{r.rank}</td>
      <th scope="row" className="py-2 pr-3 text-left font-semibold">
        <span className="mr-2 inline-block h-3 w-1 rounded-sm align-middle" style={{ background: "var(--accent)" }} />
        <Link lang="en" href={`/teams/${r.code}?season=${season}`} prefetch={false} className="hover:text-accent-text">{r.name}</Link>
      </th>
      <td className="num px-2 text-right text-muted">{r.games}</td>
      <td className="num px-2 text-right font-bold">{r.wins}</td>
      <td className="num px-2 text-right">{r.losses}</td>
      <td className="num px-2 text-right">{r.diff > 0 ? `+${r.diff}` : r.diff}</td>
      <td className="num hidden px-2 text-right text-muted sm:table-cell">{r.scored}</td>
      <td className="num hidden px-2 text-right text-muted sm:table-cell">{r.allowed}</td>
      <td className="num hidden px-2 text-right text-muted md:table-cell">{r.home}</td>
      <td className="num hidden px-2 text-right text-muted md:table-cell">{r.away}</td>
      <td className="hidden px-2 md:table-cell"><Form results={r.last5} /></td>
      <td className="num hidden px-2 text-right text-muted md:table-cell">{r.streak}</td>
    </tr>
  );
}

async function Table({ searchParams }: { searchParams: PageProps<"/standings">["searchParams"] }) {
  const sp = await searchParams;
  const meta = await getMeta();
  const season = typeof sp.season === "string" ? sp.season : meta.latest;
  const { table } = await getStandings(season);
  const lastPlayoff = table.filter((r) => r.zone === "playoff").at(-1)?.rank;
  const lastPlayIn = table.filter((r) => r.zone === "playin").at(-1)?.rank;
  return (
    <>
      <nav className="flex gap-5" aria-label="Sezon">
        {meta.seasons.map((s) => (
          <Link key={s} href={`/standings?season=${s}`} prefetch={false} aria-selected={s === season} className="tab !text-base">{seasonLabel(s)}</Link>
        ))}
      </nav>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-sm">
          <thead>
            <tr className="border-b-2 border-ink text-xs text-muted">
              <th scope="col" className="py-1 pr-2 text-right font-semibold">#</th>
              <th scope="col" className="py-1 pr-3 text-left font-semibold">Takım</th>
              <th scope="col" className="px-2 text-right font-semibold" title="Oynanan maç">O</th>
              <th scope="col" className="px-2 text-right font-semibold" title="Galibiyet">G</th>
              <th scope="col" className="px-2 text-right font-semibold" title="Mağlubiyet">M</th>
              <th scope="col" className="px-2 text-right font-semibold" title="Sayı averajı, uzatmalar hariç">Av.</th>
              <th scope="col" className="hidden px-2 text-right font-semibold sm:table-cell">Attı</th>
              <th scope="col" className="hidden px-2 text-right font-semibold sm:table-cell">Yedi</th>
              <th scope="col" className="hidden px-2 text-right font-semibold md:table-cell">İç saha</th>
              <th scope="col" className="hidden px-2 text-right font-semibold md:table-cell">Deplasman</th>
              <th scope="col" className="hidden px-2 text-left font-semibold md:table-cell">Son 5</th>
              <th scope="col" className="hidden px-2 text-right font-semibold md:table-cell">Seri</th>
            </tr>
          </thead>
          <tbody>
            {table.map((r) => <Row key={r.code} r={r} season={season} divider={r.rank === lastPlayoff || r.rank === lastPlayIn} />)}
          </tbody>
        </table>
      </div>
      <p className="max-w-[75ch] text-xs text-dim">
        İlk {lastPlayoff} takım play-off&apos;a, {(lastPlayoff ?? 0) + 1}-{lastPlayIn}. sıralar play-in&apos;e gider (kalın çizgiler). Eşitlikte, takımlar birbiriyle iki maçı da oynadıysa aralarındaki maçlara, aksi halde sayı averajına bakılır. Averaja uzatmalar girmez, bu yüzden Attı ve Yedi farkıyla ayrışabilir.
      </p>
    </>
  );
}
