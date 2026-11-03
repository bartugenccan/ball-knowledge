import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Skeleton } from "@/components/Skeleton";
import { getMeta, getTeam } from "@/lib/api";
import { overall, properName, seasonLabel, tone } from "@/lib/format";

export async function generateMetadata({ params, searchParams }: PageProps<"/teams/[code]">): Promise<Metadata> {
  const { code } = await params;
  const sp = await searchParams;
  const t = await getTeam(code, typeof sp.season === "string" ? sp.season : undefined);
  return { title: t.name };
}

export default function TeamPage(props: PageProps<"/teams/[code]">) {
  return (
    <Suspense fallback={<Skeleton className="h-[600px]" />}>
      <TeamContent {...props} />
    </Suspense>
  );
}

async function TeamContent({ params, searchParams }: PageProps<"/teams/[code]">) {
  const { code } = await params;
  const sp = await searchParams;
  const season = typeof sp.season === "string" ? sp.season : undefined;
  const [meta, t] = await Promise.all([getMeta(), getTeam(code, season)]);
  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <p className="text-muted">{seasonLabel(t.season)}</p>
        <h1 lang="en" className="font-display text-5xl font-extrabold uppercase tracking-tight md:text-6xl">{t.name}</h1>
      </header>
      <div className="panel max-h-[75vh] overflow-auto">
        <table className="data-table w-full text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-panel px-4 py-3 text-left">OYUNCU</th>
              <th className="px-2 py-3">M</th>
              <th className="px-2 py-3">DK/M</th>
              <th className="px-2 py-3">GENEL</th>
              {meta.attributes.map((a) => (
                <th key={a.key} className="px-1.5 py-3" title={a.description}>
                  <span className="block max-w-[5rem] truncate">{a.label.toLocaleUpperCase("tr")}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {t.roster.map((p, i) => {
              const ovr = overall(meta.attributes.map((a) => ({ key: a.key, value: Number(p[a.key]), conf: 1 })));
              return (
                <tr key={p.player_id} className={`rise border-t border-line/60 ${p.qualified ? "" : "opacity-50"}`} style={{ ["--i" as string]: i }}>
                  <td className="sticky left-0 whitespace-nowrap bg-panel px-4 py-2">
                    <Link href={`/players/${p.player_id}?season=${t.season}`} className="font-medium hover:text-accent">
                      {properName(String(p.player))}
                    </Link>
                  </td>
                  <td className="px-2 py-2 text-center text-muted">{p.games}</td>
                  <td className="px-2 py-2 text-center text-muted">{Number(p.mpg).toFixed(1)}</td>
                  <td className="px-2 py-2 text-center"><span className={`font-display text-lg font-bold ${tone(ovr)}`}>{ovr}</span></td>
                  {meta.attributes.map((a) => {
                    const v = Number(p[a.key]);
                    return (
                      <td key={a.key} className="px-1 py-1.5 text-center">
                        <span className={`chip-${tone(v)} inline-grid h-7 w-8 place-items-center rounded-lg font-display text-base font-bold`}>{v}</span>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-dim">Soluk satırlar az süre alan oyunculardır, puanları düşük güvenlidir.</p>
    </div>
  );
}
