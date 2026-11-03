import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Skeleton } from "@/components/Skeleton";
import { getMeta, getPlayers } from "@/lib/api";
import { GROUP_LABEL, overall, properName, seasonLabel, tone } from "@/lib/format";
import type { Group } from "@/lib/types";

export const metadata: Metadata = { title: "Oyuncular" };

type SP = Promise<Record<string, string | string[] | undefined>>;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

export default function PlayersPage({ searchParams }: { searchParams: SP }) {
  return (
    <div className="space-y-6">
      <h1 className="font-display text-5xl font-extrabold uppercase tracking-tight">Oyuncular</h1>
      <Suspense fallback={<Skeleton className="h-[600px]" />}>
        <PlayersTable searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function PlayersTable({ searchParams }: { searchParams: SP }) {
  const sp = await searchParams;
  const meta = await getMeta();
  const season = one(sp.season) ?? meta.latest;
  const group = (one(sp.group) as Group) ?? "hucum";
  const sort = one(sp.sort) ?? "minutes";
  const q = one(sp.q);
  const { players } = await getPlayers({ season, sort, q, limit: "400" });
  const attrs = meta.attributes.filter((a) => a.group === group);
  const href = (patch: Record<string, string>) =>
    `/players?${new URLSearchParams({ season, group, sort, ...(q ? { q } : {}), ...patch })}`;
  const withOvr = players.map((p) => ({
    p,
    ovr: overall(meta.attributes.map((a) => ({ key: a.key, value: Number(p[a.key]), conf: 1 }))),
  }));

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex gap-1 rounded-full border border-line bg-bg-2 p-1 text-sm" role="tablist">
          {(Object.keys(GROUP_LABEL) as Group[]).map((g) => (
            <Link key={g} href={href({ group: g })} role="tab" aria-selected={g === group}
              className={`pill px-4 py-1.5 ${g === group ? "bg-accent text-accent-ink" : "text-muted hover:text-ink"}`}>
              {GROUP_LABEL[g]}
            </Link>
          ))}
        </div>
        <form className="flex flex-wrap items-end gap-2 text-sm" action="/players">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs text-muted">Sezon</span>
            <select name="season" defaultValue={season} className="field px-3 py-2">
              {meta.seasons.map((s) => <option key={s} value={s}>{seasonLabel(s)}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1.5">
            <span className="text-xs text-muted">Oyuncu ara</span>
            <input name="q" defaultValue={q} placeholder="ör. Campazzo" className="field w-48 px-3 py-2" />
          </label>
          <input type="hidden" name="group" value={group} />
          <input type="hidden" name="sort" value={sort} />
          <button className="btn-accent px-4 py-2">Uygula</button>
        </form>
      </div>

      <div className="panel max-h-[75vh] overflow-auto">
        <table className="data-table w-full text-sm">
          <thead>
            <tr className="text-left">
              <th className="px-4 py-3">OYUNCU</th>
              <th className="px-2 py-3">TAKIM</th>
              <SortTh label="M" k="games" sort={sort} href={href} />
              <SortTh label="DK/M" k="mpg" sort={sort} href={href} />
              <th className="px-2 py-3 text-center">GENEL</th>
              {attrs.map((a) => <SortTh key={a.key} label={a.label.toLocaleUpperCase("tr")} k={a.key} sort={sort} href={href} />)}
            </tr>
          </thead>
          <tbody>
            {withOvr.map(({ p, ovr }, i) => (
              <tr key={p.player_id} className="rise border-t border-line/60" style={{ ["--i" as string]: i }}>
                <td className="whitespace-nowrap px-4 py-2">
                  <Link href={`/players/${p.player_id}?season=${season}`} className="font-medium hover:text-accent">
                    {properName(p.player)}
                  </Link>
                </td>
                <td className="px-2 py-2 text-muted">
                  <Link href={`/teams/${p.team}?season=${season}`} className="hover:text-ink">{p.team}</Link>
                </td>
                <td className="px-2 py-2 text-center text-muted">{p.games}</td>
                <td className="px-2 py-2 text-center text-muted">{Number(p.mpg).toFixed(1)}</td>
                <td className="px-2 py-2 text-center">
                  <span className={`font-display text-lg font-bold ${tone(ovr)}`}>{ovr}</span>
                </td>
                {attrs.map((a) => {
                  const v = Number(p[a.key]);
                  return (
                    <td key={a.key} className="px-2 py-1.5 text-center">
                      <span className={`chip-${tone(v)} inline-grid h-7 w-9 place-items-center rounded-lg font-display text-base font-bold`}>{v}</span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        {players.length === 0 && (
          <p className="p-6 text-center text-sm text-muted">Bu aramayla eşleşen oyuncu yok. Farklı bir isim deneyin.</p>
        )}
      </div>
      <p className="text-xs text-dim">
        Sezonun en çok süre alan oyuncusunun en az %15&apos;i kadar oynamış oyuncular listelenir. Sütun başlığına tıklayarak sıralayın.
      </p>
    </>
  );
}

function SortTh({ label, k, sort, href }: { label: string; k: string; sort: string; href: (p: Record<string, string>) => string }) {
  const active = sort === k;
  return (
    <th className="px-2 py-3 text-center" aria-sort={active ? "descending" : "none"}>
      <Link href={href({ sort: k })} className={`whitespace-nowrap transition-colors hover:text-ink ${active ? "text-accent" : ""}`}>
        {label}
        {active && " ↓"}
      </Link>
    </th>
  );
}
