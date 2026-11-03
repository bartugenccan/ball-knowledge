import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Stagger, StaggerItem } from "@/components/motion/Reveal";
import { Spotlight } from "@/components/motion/Spotlight";
import { Skeleton } from "@/components/Skeleton";
import { getMeta, getTeams } from "@/lib/api";
import { seasonLabel, tone } from "@/lib/format";

export const metadata: Metadata = { title: "Takımlar" };

const SHOW = [
  ["three_point", "Üçlük"],
  ["finishing", "Bitiricilik"],
  ["passing", "Pas"],
  ["team_defense", "Savunma"],
  ["def_rebounding", "Ribaund"],
] as const;

export default function TeamsPage({ searchParams }: PageProps<"/teams">) {
  return (
    <div className="space-y-6">
      <h1 className="font-display text-5xl font-extrabold uppercase tracking-tight">Takımlar</h1>
      <Suspense fallback={<Skeleton className="h-[600px]" />}>
        <TeamsGrid searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function TeamsGrid({ searchParams }: { searchParams: PageProps<"/teams">["searchParams"] }) {
  const sp = await searchParams;
  const meta = await getMeta();
  const season = typeof sp.season === "string" ? sp.season : meta.latest;
  const { teams } = await getTeams(season);
  // team averages sit in a narrow band, so colour each column by the team's standing among teams
  const relTone = (k: string, v: number) => {
    const vals = teams.map((t) => t.avg[k] ?? 0);
    const mean = vals.reduce((s, x) => s + x, 0) / vals.length;
    const sd = Math.sqrt(vals.reduce((s, x) => s + (x - mean) ** 2, 0) / vals.length) || 1;
    return tone(Math.round(11.5 + (3.2 * (v - mean)) / sd));
  };
  return (
    <>
      <p className="text-muted">{seasonLabel(season)} sezonu, rotasyon oyuncularının ortalama özellikleri. Renk, takımlar arasındaki sırayı gösterir.</p>
      <Stagger className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {teams.map((t) => (
          <StaggerItem key={t.code}>
            <Link href={`/teams/${t.code}?season=${season}`} className="block h-full">
              <Spotlight className="group h-full p-5 transition-transform duration-300 hover:-translate-y-1">
                <div className="flex items-start justify-between gap-2">
                  <h2 lang="en" className="font-display text-2xl font-bold uppercase leading-tight transition-colors group-hover:text-accent">{t.name}</h2>
                  <span className="rounded-full border border-line-2 px-2 py-0.5 font-mono text-xs text-muted">{t.code}</span>
                </div>
                <dl className="mt-4 grid grid-cols-5 gap-2">
                  {SHOW.map(([k, l]) => {
                    const v = t.avg[k] ?? 0;
                    return (
                      <div key={k} className="text-center">
                        <dd className={`font-display text-2xl font-bold ${relTone(k, v)}`}>{v.toFixed(1)}</dd>
                        <dt className="text-[10px] text-dim">{l}</dt>
                      </div>
                    );
                  })}
                </dl>
              </Spotlight>
            </Link>
          </StaggerItem>
        ))}
      </Stagger>
    </>
  );
}
