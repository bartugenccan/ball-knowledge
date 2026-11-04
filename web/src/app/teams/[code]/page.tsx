import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Koreografi } from "@/components/motion/Koreografi";
import { Skeleton } from "@/components/Skeleton";
import { getMeta, getTeam } from "@/lib/api";
import { clubVars } from "@/lib/clubs";
import { GROUP_LABEL, hintText, overall, properName, seasonLabel, shortLabel, tone } from "@/lib/format";
import type { Group } from "@/lib/types";

export async function generateMetadata({ params, searchParams }: PageProps<"/teams/[code]">): Promise<Metadata> {
  const { code } = await params;
  const sp = await searchParams;
  const t = await getTeam(code, typeof sp.season === "string" ? sp.season : undefined);
  return { title: t.name };
}

export default function TeamPage(props: PageProps<"/teams/[code]">) {
  return (
    <Suspense fallback={<div className="wrap pt-8"><Skeleton className="h-[600px]" /></div>}>
      <TeamContent {...props} />
    </Suspense>
  );
}

async function TeamContent({ params, searchParams }: PageProps<"/teams/[code]">) {
  const { code } = await params;
  const sp = await searchParams;
  const season = typeof sp.season === "string" ? sp.season : undefined;
  const [meta, t] = await Promise.all([getMeta(), getTeam(code, season)]);
  const groups = Object.keys(GROUP_LABEL) as Group[];
  const attrs = groups.flatMap((g) => meta.attributes.filter((a) => a.group === g));
  return (
    <div className="club" style={clubVars(t.code)}>
      <div className="on-stand h-[30dvh] min-h-[180px] max-h-[320px]">
        <Koreografi frames={[{ text: t.code, tone: "bone" }]} />
      </div>
      <div className="wrap space-y-6 pt-8">
        <header>
          <p className="mb-1 text-muted">{seasonLabel(t.season)}</p>
          <h1 lang="en" className="display stretch-in text-[clamp(2.8rem,6.6vw,5.8rem)]">{t.name}</h1>
        </header>
        <div className="max-h-[80vh] overflow-auto">
          <table className="mosaic w-full text-sm">
            <thead>
              <tr>
                <th scope="col" className="sticky left-0 z-[3] px-2 py-2 text-left align-bottom">OYUNCU</th>
                <th scope="col" className="hidden px-1 py-2 align-bottom sm:table-cell"><span className="th-rot">MAÇ</span></th>
                <th scope="col" className="hidden px-1 py-2 align-bottom sm:table-cell"><span className="th-rot">DK/M</span></th>
                <th scope="col" className="px-0 py-2 align-bottom"><span className="th-rot">GENEL</span></th>
                {attrs.map((a) => (
                  <th key={a.key} scope="col" className="px-0 py-2 align-bottom" title={hintText(a)}>
                    <span className="th-rot">{a.label}</span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {t.roster.map((p, i) => {
                const ovr = overall(meta.attributes.map((a) => ({ key: a.key, value: Number(p[a.key]), conf: 1 })));
                return (
                  <tr key={p.player_id} className={p.qualified ? "" : "opacity-55"}>
                    <td className="sticky left-0 z-[1] max-w-36 truncate whitespace-nowrap px-2 py-1 sm:max-w-none">
                      <Link href={`/players/${p.player_id}?season=${t.season}`} lang="en" prefetch={false} className="font-semibold hover:text-accent-text">
                        {properName(String(p.player))}
                      </Link>
                    </td>
                    <td className="hidden px-1 py-1 text-center text-muted sm:table-cell">{p.games}</td>
                    <td className="hidden px-1 py-1 text-center text-muted sm:table-cell">{Number(p.mpg).toFixed(1)}</td>
                    <td className={`tile tile-${tone(ovr)} wave !font-black`} style={{ ["--d" as string]: i }}>{ovr}</td>
                    {attrs.map((a) => {
                      const v = Number(p[a.key]);
                      const label = p.labels[a.key];
                      if (label && shortLabel(label) === "–") {
                        return <td key={a.key} className="tile wave text-dim" title={label} style={{ ["--d" as string]: i }}>–</td>;
                      }
                      if (label) {
                        return <td key={a.key} className={`tile tile-${tone(v)} wave`} title={label} style={{ ["--d" as string]: i }}>{shortLabel(label)}</td>;
                      }
                      return (
                        <td key={a.key} className={`tile tile-${tone(v)} wave`} style={{ ["--d" as string]: i }}>{v}</td>
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
    </div>
  );
}
