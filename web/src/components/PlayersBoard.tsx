"use client";

import { MagnifyingGlass } from "@phosphor-icons/react";
import Link from "next/link";
import { memo, useCallback, useDeferredValue, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { clubVars } from "@/lib/clubs";
import { GROUP_LABEL, hintText, shortLabel, tone } from "@/lib/format";
import type { AttributeMeta, Group } from "@/lib/types";

export type BoardRow = {
  id: string;
  name: string;
  team: string;
  games: number;
  mpg: number;
  ovr: number;
  vals: Record<string, number>;
  labels: Record<string, string>;
};

/** Must match `.mosaic-fixed tbody td` in globals.css. Everything below depends on rows being this tall. */
const ROW_H = 33;
/** Enough for the tallest scroller (78vh) plus overscan on both sides. */
const WINDOW_ROWS = 56;
/** Only re-window every few rows, so scrolling does not re-render on every pixel. */
const STEP_ROWS = 8;

// Turkish and foreign spellings should match each other: "sanli" finds "Şanlı".
const fold = (s: string) =>
  s
    .toLocaleLowerCase("tr")
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/ı/g, "i");

const Row = memo(function Row({ r, season, keys, register }: {
  r: BoardRow;
  season: string;
  keys: string[];
  register: (id: string) => (el: HTMLElement | null) => void;
}) {
  const ref = useMemo(() => register(r.id), [register, r.id]);
  return (
    <tr ref={ref} className="club" style={clubVars(r.team)}>
      <td className="sticky left-0 z-[1] truncate whitespace-nowrap px-2">
        <Link href={`/players/${r.id}?season=${season}`} lang="en" prefetch={false} className="font-semibold hover:text-accent-text">{r.name}</Link>
      </td>
      <td className="hidden px-2 text-center text-muted sm:table-cell">
        <Link href={`/teams/${r.team}?season=${season}`} prefetch={false} className="hover:text-ink">{r.team}</Link>
      </td>
      <td className="hidden px-2 text-center text-muted sm:table-cell">{r.games}</td>
      <td className="hidden px-2 text-center text-muted sm:table-cell">{r.mpg.toFixed(1)}</td>
      <td className={`tile tile-${tone(r.ovr)} !font-black`}>{r.ovr}</td>
      {keys.map((k) => {
        const label = r.labels[k];
        if (label && shortLabel(label) === "–") return <td key={k} className="tile text-dim" title={label}>–</td>;
        return <td key={k} className={`tile tile-${tone(r.vals[k])}`} title={label}>{label ? shortLabel(label) : r.vals[k]}</td>;
      })}
    </tr>
  );
});

/**
 * The player table as a mosaic. Sorting happens here, not on the server, so rows can shuffle
 * like a league table; the URL is kept in sync so a view can still be shared.
 *
 * Only the rows on screen exist in the DOM. Rows have a fixed height, so the shuffle works out
 * its distances from the sort order and never has to measure a 3,000-cell table.
 */
export function PlayersBoard({
  rows,
  attributes,
  season,
  initial,
}: {
  rows: BoardRow[];
  attributes: AttributeMeta[];
  season: string;
  initial: { group: Group; sort: string; q: string };
}) {
  const [group, setGroup] = useState(initial.group);
  const [sort, setSort] = useState(initial.sort);
  const [q, setQ] = useState(initial.q);
  const [first, setFirst] = useState(0);
  const [wave, setWave] = useState(0);
  const deferredQ = useDeferredValue(q);
  const attrs = useMemo(() => attributes.filter((a) => a.group === group), [attributes, group]);
  const keys = useMemo(() => attrs.map((a) => a.key), [attrs]);

  const sync = (patch: Partial<{ group: string; sort: string; q: string }>) => {
    const next = { group, sort, q, ...patch };
    const params = new URLSearchParams({ season, group: next.group, sort: next.sort, ...(next.q ? { q: next.q } : {}) });
    window.history.replaceState(null, "", `/players?${params}`);
  };
  const onSort = (k: string) => {
    setSort(k);
    sync({ sort: k });
  };

  const shown = useMemo(() => {
    const needle = fold(deferredQ.trim());
    const list = needle ? rows.filter((r) => fold(r.name).includes(needle)) : rows;
    const val = (r: BoardRow) => (sort === "ovr" ? r.ovr : sort === "games" ? r.games : sort === "mpg" ? r.mpg : (r.vals[sort] ?? 0));
    return [...list].sort((a, b) => val(b) - val(a) || b.mpg - a.mpg);
  }, [rows, deferredQ, sort]);

  const start = Math.min(first, Math.max(0, shown.length - WINDOW_ROWS));
  const visible = useMemo(() => shown.slice(start, start + WINDOW_ROWS), [shown, start]);

  // League-table shuffle: slide from the old position, derived from indexes, not from layout.
  const rowEls = useRef(new Map<string, HTMLElement>());
  const prevIndex = useRef(new Map<string, number>());
  const register = useCallback(
    (id: string) => (el: HTMLElement | null) => {
      if (el) rowEls.current.set(id, el);
      else rowEls.current.delete(id);
    },
    [],
  );
  useLayoutEffect(() => {
    const next = new Map(shown.map((r, i) => [r.id, i]));
    if (prevIndex.current.size && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      let n = 0;
      rowEls.current.forEach((el, id) => {
        const from = prevIndex.current.get(id);
        const to = next.get(id);
        if (from === undefined || to === undefined || from === to) return;
        const dy = Math.max(-640, Math.min(640, (from - to) * ROW_H));
        el.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], {
          duration: 520,
          delay: Math.min(n++, 24) * 9,
          easing: "cubic-bezier(0.2, 1.15, 0.35, 1)",
          fill: "backwards",
        });
      });
    }
    prevIndex.current = next;
  }, [shown]);

  // The wave of cards on a tab switch only needs to run once, then the attribute comes off.
  useEffect(() => {
    if (!wave) return;
    const t = setTimeout(() => setWave(0), 700);
    return () => clearTimeout(t);
  }, [wave]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <div className="flex gap-5" role="tablist" aria-label="Özellik grubu">
          {(Object.keys(GROUP_LABEL) as Group[]).map((g) => (
            <button
              key={g}
              type="button"
              role="tab"
              aria-selected={g === group}
              className="tab"
              onClick={() => {
                const staleSort = attributes.some((a) => a.key === sort && a.group !== g);
                const nextSort = staleSort ? "ovr" : sort;
                setGroup(g);
                setSort(nextSort);
                setWave((n) => n + 1);
                sync({ group: g, sort: nextSort });
              }}
            >
              {GROUP_LABEL[g]}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <MagnifyingGlass size={18} weight="bold" aria-hidden />
          <span className="sr-only">Oyuncu ara</span>
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              sync({ q: e.target.value });
            }}
            placeholder="Oyuncu ara"
            className="field w-52"
          />
        </label>
      </div>

      <div
        className="max-h-[78vh] overflow-auto"
        onScroll={(e) => {
          const row = Math.floor(e.currentTarget.scrollTop / ROW_H);
          const next = Math.max(0, Math.floor(row / STEP_ROWS) * STEP_ROWS - STEP_ROWS);
          if (next !== first) setFirst(next);
        }}
      >
        <table className="mosaic mosaic-fixed w-full text-sm" data-wave={wave ? "true" : undefined} aria-rowcount={shown.length + 1} style={{ minWidth: `calc(9rem + ${keys.length + 1} * 2.25rem)` }}>
          <thead>
            <tr>
              <th scope="col" className="sticky left-0 z-[3] w-36 px-2 py-2 text-left align-bottom sm:w-56">OYUNCU</th>
              <th scope="col" className="hidden w-16 px-2 py-2 align-bottom sm:table-cell">TAKIM</th>
              <SortTh label="MAÇ" k="games" sort={sort} className="hidden w-14 sm:table-cell" onSort={onSort} />
              <SortTh label="DK/M" k="mpg" sort={sort} className="hidden w-14 sm:table-cell" onSort={onSort} />
              <SortTh label="GENEL" k="ovr" sort={sort} onSort={onSort} />
              {attrs.map((a) => (
                <SortTh key={a.key} label={a.label} k={a.key} sort={sort} onSort={onSort} title={hintText(a)} />
              ))}
            </tr>
          </thead>
          <tbody>
            <tr aria-hidden style={{ height: start * ROW_H }} />
            {visible.map((r) => (
              <Row key={r.id} r={r} season={season} keys={keys} register={register} />
            ))}
            <tr aria-hidden style={{ height: Math.max(0, shown.length - start - visible.length) * ROW_H }} />
          </tbody>
        </table>
        {shown.length === 0 && (
          <p className="py-10 text-center text-muted">Bu aramayla eşleşen oyuncu yok. Farklı bir isim deneyin.</p>
        )}
      </div>
      <p className="text-xs text-dim">
        Sezonun en çok süre alan oyuncusunun en az %15&apos;i kadar oynamış oyuncular listelenir. Sütun başlığına tıklayarak sıralayın.
      </p>
    </div>
  );
}

function SortTh({ label, k, sort, onSort, title, className = "" }: { label: string; k: string; sort: string; onSort: (k: string) => void; title?: string; className?: string }) {
  return (
    <th scope="col" className={`px-0 py-2 align-bottom ${className}`} aria-sort={sort === k ? "descending" : "none"}>
      <button type="button" title={title} onClick={() => onSort(k)} className="th-rot cursor-pointer">
        {label}
        {sort === k && " ↓"}
      </button>
    </th>
  );
}
