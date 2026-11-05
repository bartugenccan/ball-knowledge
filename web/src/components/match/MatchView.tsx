"use client";

import { useState } from "react";
import { COURT_H, COURT_W, CourtLines, tx, ty } from "@/components/Court";
import { MarginChart } from "@/components/match/MarginChart";
import { PlayByPlay, SideBySide } from "@/components/match/PlayByPlay";
import { clubPair } from "@/lib/clubs";
import type { Band, BoxRow, CoachNote, CompareRow, Comparison, Edge, GameEvent, Gap, MatchReport, Moment, PlayerLine, Scenario, StoryPart } from "@/lib/match";

const STAT_LABEL: Record<string, string> = {
  pts: "Sayı", poss: "Hücum sayısı", efg: "Şut verimi (eFG%)", three_pct: "Üçlük %", two_pct: "İkilik %", f3a: "Üçlük denemesi", inside_a: "Boyalı alan şutu",
  mid_a: "Orta mesafe şutu", fta: "Serbest atış", tov: "Top kaybı", orb: "Hücum ribaundu", drb: "Savunma ribaundu", ast: "Asist", stl: "Top çalma", blk: "Blok", pf: "Faul",
};
const GAP_LABEL: Record<string, string> = {
  three_accuracy: "üçlük isabeti", two_accuracy: "iki sayılık isabeti", three_volume: "üçlük sayısı", two_volume: "iki sayılık şut sayısı", free_throws: "serbest atış",
};
const ATTRIBUTE_LABEL: Record<string, string> = {
  three_point: "Üçlük", finishing: "Bitiricilik", steals: "Top Çalma", off_rebounding: "Hücum Ribaundu", def_rebounding: "Savunma Ribaundu", drawing_fouls: "Faul Alma", free_throw: "Serbest Atış",
};
const NOTABLE_ATTRIBUTES: { key: string; label: string }[] = [
  { key: "three_point", label: "Üçlük" }, { key: "finishing", label: "Bitiricilik" }, { key: "passing", label: "Pas" }, { key: "shot_creation", label: "Şut Yaratma" },
  { key: "off_rebounding", label: "Hüc. Rib." }, { key: "def_rebounding", label: "Sav. Rib." }, { key: "steals", label: "Top Çalma" }, { key: "rim_protection", label: "Pota" },
];

type View = "typical" | "other" | "real";

function Scoreboard({ label, home, away, r, emphasis }: { label: string; home: number; away: number; r: MatchReport; emphasis?: boolean }) {
  return (
    <div className={`rounded-md border p-3 ${emphasis ? "border-ink" : "border-line"}`}>
      <p className="text-xs font-semibold text-muted">{label}</p>
      <p className="num mt-1 flex items-baseline gap-2 text-4xl">
        <span style={{ color: "var(--side-a-t)" }}>{home}</span>
        <span className="text-xl text-dim">–</span>
        <span style={{ color: "var(--side-b-t)" }}>{away}</span>
      </p>
      <p className="mt-0.5 text-xs text-muted">{r.home.code} – {r.away.code}</p>
    </div>
  );
}

function bandText(b: Band) {
  return `${Math.round(b.lo)}–${Math.round(b.hi)}`;
}

function marginBandText(b: Band, home: string, away: string) {
  const side = (v: number) => (v === 0 ? "beraber" : v > 0 ? `${home} +${Math.round(v)}` : `${away} +${Math.round(-v)}`);
  return `${side(b.lo)} ile ${side(b.hi)} arası`;
}

function Moments({ list }: { list: Moment[] }) {
  if (!list.length) return <p className="text-sm text-muted">Maçı kıran belirgin bir seri ya da an yok.</p>;
  return (
    <ol className="space-y-1.5">
      {list.map((m, i) => (
        <li key={i} className="flex gap-3 text-sm">
          <span className="num w-10 shrink-0 text-xs text-dim">{m.clock}</span>
          <span lang="en">{m.text}</span>
        </li>
      ))}
    </ol>
  );
}

function Story({ parts }: { parts: StoryPart[] }) {
  return (
    <div className="grid gap-x-10 gap-y-5 md:grid-cols-2">
      {parts.map((p) => (
        <div key={p.title} className="border-t-2 border-ink pt-2">
          <h3 className="mb-1 font-semibold">{p.title}</h3>
          <p lang="tr" className="text-[1.02rem] leading-relaxed">{p.text}</p>
        </div>
      ))}
    </div>
  );
}

function Coach({ notes }: { notes: CoachNote[] }) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {notes.map((n, i) => (
        <div key={n.team}>
          <h3 className="mb-1 font-bold" style={{ color: i === 0 ? "var(--side-a-t)" : "var(--side-b-t)" }}>{n.team}</h3>
          <ul className="list-disc space-y-1 pl-5">
            {n.items.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>
      ))}
    </div>
  );
}

function BoxTable({ code, rows }: { code: string; rows: BoxRow[] }) {
  return (
    <div className="overflow-x-auto">
      <p className="mb-1 font-semibold">{code}</p>
      <table className="w-full min-w-[560px] text-sm">
        <thead>
          <tr className="border-b-2 border-ink text-left text-xs text-muted">
            <th scope="col" className="py-1 pr-2 font-semibold">Oyuncu</th>
            {["Dk", "Sayı", "Rib", "Ast", "Çal", "Blk", "Kyb", "Fl", "2S", "3S", "SA"].map((h) => (
              <th key={h} scope="col" className="px-1 py-1 text-right font-semibold">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.player_id} className="border-b border-line">
              <th scope="row" lang="en" className="whitespace-nowrap py-1 pr-2 text-left font-semibold">{r.name}</th>
              <td className="num px-1 text-right text-muted">{r.min.toFixed(0)}</td>
              <td className="num px-1 text-right font-bold">{r.pts}</td>
              <td className="num px-1 text-right">{r.reb}</td>
              <td className="num px-1 text-right">{r.ast}</td>
              <td className="num px-1 text-right">{r.stl}</td>
              <td className="num px-1 text-right">{r.blk}</td>
              <td className="num px-1 text-right">{r.tov}</td>
              <td className="num px-1 text-right">{r.pf}</td>
              <td className="num px-1 text-right text-muted">{r.f2}</td>
              <td className="num px-1 text-right text-muted">{r.f3}</td>
              <td className="num px-1 text-right text-muted">{r.ft}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ShotMap({ events, code, color }: { events: GameEvent[]; code: string; color: string }) {
  const shots = events.filter((e) => e.team === code && (e.event === "make" || e.event === "miss") && e.coord && ty(e.coord[1]) < COURT_H);
  const made = shots.filter((s) => s.event === "make").length;
  return (
    <figure>
      <figcaption className="mb-1 flex justify-between text-sm"><span className="font-semibold">{code}</span><span className="text-muted">{made}/{shots.length} şut</span></figcaption>
      <svg viewBox={`0 0 ${COURT_W} ${COURT_H}`} className="w-full rounded-md bg-bg-2" role="img" aria-label={`${code} şut haritası: ${shots.length} şut, ${made} isabet`}>
        <CourtLines stroke="var(--line)" rim="var(--dim)" paint="transparent" />
        {shots.map((s, i) => {
          const [x, y] = s.coord as [number, number];
          return s.event === "make"
            ? <circle key={i} cx={tx(x)} cy={ty(y)} r={22} fill={color} stroke="var(--bg-2)" strokeWidth={5}><title>{s.text}</title></circle>
            : <path key={i} d={`M${tx(x) - 15} ${ty(y) - 15}L${tx(x) + 15} ${ty(y) + 15}M${tx(x) + 15} ${ty(y) - 15}L${tx(x) - 15} ${ty(y) + 15}`} stroke="var(--dim)" strokeWidth={7} strokeLinecap="round"><title>{s.text}</title></path>;
        })}
      </svg>
    </figure>
  );
}

/** Which side a factor favors, in points, with the regulars the ratings single out for it. */
function Edges({ edges, home, away }: { edges: Edge[]; home: string; away: string }) {
  const peak = Math.max(3, ...edges.map((e) => Math.abs(e.points)));
  const leaders = (e: Edge, code: string) => e.leaders[code]?.map((l) => `${l.name} (${ATTRIBUTE_LABEL[l.attribute] ?? l.attribute} ${l.label ?? l.rating})`).join(", ");
  return (
    <ul className="space-y-5">
      {edges.map((e) => {
        const w = (100 * Math.min(Math.abs(e.points), peak)) / peak / 2;
        const toHome = e.points >= 0;
        const size = Math.abs(e.points).toFixed(1);
        const gap = size === "0.0" ? "Fark yok" : `${size} sayı ${toHome ? home : away} lehine`;
        return (
          <li key={e.key}>
            <div className="grid grid-cols-[4.5rem_1fr_4.5rem] items-baseline gap-2">
              <span className="num text-right text-lg" style={{ color: "var(--side-a-t)" }}>{e.home}{e.unit}</span>
              <span className="text-center text-sm font-semibold">{e.label}</span>
              <span className="num text-lg" style={{ color: "var(--side-b-t)" }}>{e.away}{e.unit}</span>
            </div>
            <div className="relative mt-1 h-2.5 rounded-sm bg-bg-2" role="img" aria-label={`${e.label}: ${gap}`}>
              <div className="absolute inset-y-0 left-1/2 w-px bg-dim" />
              <div
                className="absolute inset-y-0 rounded-sm"
                style={toHome ? { right: "50%", width: `${w}%`, background: "var(--side-a)" } : { left: "50%", width: `${w}%`, background: "var(--side-b)" }}
              />
            </div>
            <p className="mt-1 flex justify-between gap-4 text-xs text-muted">
              <span lang="en">{leaders(e, home)}</span>
              <span className="whitespace-nowrap font-medium text-ink">{gap}</span>
              <span lang="en" className="text-right">{leaders(e, away)}</span>
            </p>
          </li>
        );
      })}
    </ul>
  );
}

function RangeCell({ row }: { row: CompareRow }) {
  const low = Math.min(row.lo, row.real);
  const high = Math.max(row.hi, row.real);
  const pad = (high - low) * 0.1 || 1;
  const at = (v: number) => `${(100 * (v - low + pad)) / (high - low + 2 * pad)}%`;
  return (
    <div className="relative h-4 min-w-24">
      <div className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-sm bg-[color-mix(in_oklab,var(--muted)_35%,transparent)]" style={{ left: at(row.lo), right: `calc(100% - ${at(row.hi)})` }} />
      <div className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-bg" style={{ left: at(row.real), background: row.in_range ? "var(--ink)" : "var(--r-poor, var(--ink))" }} />
    </div>
  );
}

function CompareTable({ c, home, away }: { c: Comparison; home: string; away: string }) {
  const stats = [...new Set(c.table.map((r) => r.stat))];
  const cell = (r: CompareRow | undefined) => r && (
    <>
      <td className={`num px-1 text-right font-semibold ${r.in_range ? "" : "underline decoration-2 underline-offset-2"}`}>{r.real.toFixed(r.real % 1 ? 1 : 0)}</td>
      <td className="num px-1 text-right text-xs text-muted">{r.lo.toFixed(0)}–{r.hi.toFixed(0)}</td>
      <td className="hidden px-2 md:table-cell"><RangeCell row={r} /></td>
    </>
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="text-xs text-muted">
            <th scope="col" className="py-1 text-left font-semibold">İstatistik</th>
            <th scope="colgroup" colSpan={3} className="px-1 text-left font-bold" style={{ color: "var(--side-a-t)" }}>{home}: gerçek / beklenen</th>
            <th scope="colgroup" colSpan={3} className="px-1 text-left font-bold" style={{ color: "var(--side-b-t)" }}>{away}: gerçek / beklenen</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((s) => (
            <tr key={s} className="border-t border-line">
              <th scope="row" className="py-1 pr-2 text-left font-medium">{STAT_LABEL[s] ?? s}</th>
              {cell(c.table.find((r) => r.stat === s && r.team === home))}
              {cell(c.table.find((r) => r.stat === s && r.team === away))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-muted">Gri şerit %80 beklenen aralık, nokta gerçek değer. Altı çizili sayılar aralığın dışında kaldı; %80 aralıkta her beş değerden birinin dışarı taşması normaldir.</p>
    </div>
  );
}

function gapSentence(g: Gap) {
  const plus = g.points >= 0;
  const unit = g.kind.endsWith("accuracy") ? "%" : "";
  return `${g.team}, ${GAP_LABEL[g.kind]}: ${g.expected}${unit} beklenirken ${typeof g.real === "number" ? g.real.toFixed(g.kind.endsWith("accuracy") ? 1 : 0) : g.real}${unit}. ${plus ? "+" : ""}${g.points.toFixed(1)} sayı`;
}

function PlayersCompare({ rows, code }: { rows: PlayerLine[]; code: string }) {
  const shown = rows.filter((r) => r.actual);
  const cell = (r: PlayerLine, key: string, simKey = key) => {
    const b = r.sim[simKey];
    const value = r.actual?.[key] ?? 0;
    const inside = r.in_range?.[key] ?? true;
    return (
      <td className="px-1 text-right">
        <span className={`num font-semibold ${inside ? "" : "underline decoration-2 underline-offset-2"}`}>{value.toFixed(0)}</span>
        <span className="num ml-1 text-xs text-muted">{Math.round(b.lo)}–{Math.round(b.hi)}</span>
      </td>
    );
  };
  return (
    <div className="overflow-x-auto">
      <p className="mb-1 font-semibold">{code}</p>
      <table className="w-full min-w-[480px] text-sm">
        <thead>
          <tr className="border-b-2 border-ink text-left text-xs text-muted">
            <th scope="col" className="py-1 font-semibold">Oyuncu</th>
            {["Dakika", "Sayı", "Ribaund", "Asist"].map((h) => <th key={h} scope="col" className="px-1 py-1 text-right font-semibold">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {shown.map((r) => (
            <tr key={r.player_id} className="border-b border-line">
              <th scope="row" lang="en" className="whitespace-nowrap py-1 pr-2 text-left font-semibold">{r.short}{r.starter && <span className="ml-1 text-xs font-normal text-dim">İ5</span>}</th>
              {cell(r, "min")}{cell(r, "pts")}{cell(r, "reb")}{cell(r, "ast")}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RatingsLine({ p }: { p: PlayerLine }) {
  const parts = NOTABLE_ATTRIBUTES
    .filter((a) => p.ratings[a.key] !== undefined && !p.low_data.includes(a.key) && (p.ratings[a.key] >= 15 || p.ratings[a.key] <= 6))
    .sort((x, y) => Math.abs(p.ratings[y.key] - 11) - Math.abs(p.ratings[x.key] - 11))
    .slice(0, 3)
    .map((a) => `${a.label} ${p.labels[a.key] ?? p.ratings[a.key]}`);
  return <span className="text-xs text-muted">{parts.join(" · ")}</span>;
}

function PlayerExpect({ rows, code }: { rows: PlayerLine[]; code: string }) {
  return (
    <div className="overflow-x-auto">
      <p className="mb-1 font-semibold">{code}</p>
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="border-b-2 border-ink text-left text-xs text-muted">
            <th scope="col" className="py-1 font-semibold">Oyuncu ve öne çıkan puanları</th>
            {["Dakika", "Sayı", "Ribaund", "Asist"].map((h) => <th key={h} scope="col" className="px-1 py-1 text-right font-semibold">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.filter((r) => r.sim.min.mean >= 5).map((r) => (
            <tr key={r.player_id} className="border-b border-line">
              <th scope="row" className="py-1 pr-2 text-left font-semibold"><span lang="en">{r.short}</span><div><RatingsLine p={r} /></div></th>
              {["min", "pts", "reb", "ast"].map((k) => (
                <td key={k} className="px-1 text-right align-top">
                  <span className="num font-semibold">{r.sim[k].mean.toFixed(k === "min" || k === "pts" ? 0 : 1)}</span>
                  <span className="num ml-1 text-xs text-muted">{Math.round(r.sim[k].lo)}–{Math.round(r.sim[k].hi)}</span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function headline(r: MatchReport): string {
  const favored = r.home_win >= 0.5 ? r.home.code : r.away.code;
  const share = Math.round(100 * Math.max(r.home_win, 1 - r.home_win));
  const close = share < 58;
  const s = r.score;
  if (close) return `Başa baş bir maç bekleniyor: ${favored} hafif önde. Beklenen skor farkı ${marginBandText(s.margin, r.home.code, r.away.code)}.`;
  return `${favored} önde başlıyor. Beklenen skor farkı ${marginBandText(s.margin, r.home.code, r.away.code)}.`;
}

function verdict(r: MatchReport, c: Comparison): string {
  const winner = c.home > c.away ? r.home.code : r.away.code;
  const first = c.favored_won ? `Kazananı doğru gördü (${winner}).` : `Kazananı yanlış gördü: maçı ${winner} aldı.`;
  const second = c.margin_in_range ? "Gerçek skor farkı beklenen aralığın içinde kaldı." : "Gerçek skor farkı beklenen aralığın dışına çıktı.";
  const third = `Gerçek farkın beklenen aralıkta geçirdiği dakika payı: %${Math.round(100 * c.minutes_in_band)}.`;
  return `${first} ${second} ${third}`;
}

export function MatchView({ r }: { r: MatchReport }) {
  const home = r.home.code;
  const away = r.away.code;
  const c = r.comparison;
  const [view, setView] = useState<View>("typical");
  const scenario: Scenario = view === "other" ? r.other : r.typical;
  const events = view === "real" && r.real ? r.real.events : scenario.events;
  const moments = view === "real" && r.real ? r.real.moments : scenario.moments;
  const story = view === "real" && r.real ? r.real.story : scenario.story;
  const underdog = r.home_win >= 0.5 ? away : home;
  const shareOther = Math.round(100 * Math.min(r.home_win, 1 - r.home_win));
  const views: { key: View; label: string }[] = [
    { key: "typical", label: "En olası senaryo" },
    { key: "other", label: `${underdog} kazanırsa` },
    ...(r.real ? [{ key: "real" as const, label: "Gerçek maç" }] : []),
  ];
  const lines = [
    { key: "scenario", label: view === "other" ? `${underdog} kazanırsa` : "En olası senaryo", values: scenario.margins, color: "var(--muted)", width: 2, dash: "6 4" },
    ...(c ? [{ key: "real", label: "Gerçek maç", values: c.margins, color: "var(--ink)", width: 2.5 }] : []),
  ];

  return (
    <div className="pair space-y-12" style={clubPair(home, away)}>
      <section className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {c && <Scoreboard label="Gerçek skor" home={c.home} away={c.away} r={r} emphasis />}
          <Scoreboard label="En olası senaryo" home={r.typical.home} away={r.typical.away} r={r} />
          <div className="rounded-md border border-line p-3 text-sm">
            <p className="text-xs font-semibold text-muted">Beklenen aralık</p>
            <p className="mt-1"><span className="font-semibold" style={{ color: "var(--side-a-t)" }}>{home}</span> {bandText(r.score.home)} sayı</p>
            <p><span className="font-semibold" style={{ color: "var(--side-b-t)" }}>{away}</span> {bandText(r.score.away)} sayı</p>
            <p className="text-muted">{underdog} kabaca her {Math.max(2, Math.round(100 / Math.max(shareOther, 1)))} maçtan birini kazanıyor.</p>
          </div>
        </div>
        <p className="max-w-[80ch] text-lg">{headline(r)}</p>
        {c && <p className="max-w-[80ch] text-muted">{verdict(r, c)}</p>}
      </section>

      <section className="space-y-3">
        <h2 className="display t-sec">Maç önü</h2>
        <p className="max-w-[80ch]">{r.tempo}</p>
        <ul className="max-w-[85ch] space-y-2">
          {r.preview.map((row) => <li key={row.key + (row.team ?? "") + row.text.slice(0, 12)}>{row.text}</li>)}
        </ul>
      </section>

      <section className="space-y-4">
        <h2 className="display t-sec">Maçın akışı</h2>
        <MarginChart home={home} away={away} band={r.minute_band} lines={lines} />
        {c && (
          <p className="max-w-[80ch] text-sm text-muted">
            Üstünlük değişimi: gerçekte {c.flow.find((f) => f.stat === "lead_changes")?.real}, beklenen {r.flow.lead_changes.lo.toFixed(0)}–{r.flow.lead_changes.hi.toFixed(0)}.
            {" "}En büyük fark gerçekte {Math.max(c.flow.find((f) => f.stat === "max_lead_home")?.real ?? 0, c.flow.find((f) => f.stat === "max_lead_away")?.real ?? 0)}.
          </p>
        )}
      </section>

      <section className="space-y-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h2 className="display t-sec">Hikâye</h2>
          <div className="flex gap-5" role="tablist" aria-label="Senaryo">
            {views.map((v) => (
              <button key={v.key} type="button" role="tab" aria-selected={view === v.key} className="tab" onClick={() => setView(v.key)}>{v.label}</button>
            ))}
          </div>
        </div>
        {view !== "real" && (
          <p className="num text-3xl">
            <span style={{ color: "var(--side-a-t)" }}>{home} {scenario.home}</span>
            <span className="mx-2 text-dim">–</span>
            <span style={{ color: "var(--side-b-t)" }}>{scenario.away} {away}</span>
            {scenario.overtime && <span className="ml-3 text-base text-muted">uzatmada</span>}
          </p>
        )}
        <Story parts={story} />
        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
          <div>
            <h3 className="display t-sub mb-2">Maçın dönüm noktaları</h3>
            <Moments list={moments} />
          </div>
          <div>
            <h3 className="display t-sub mb-2">Play-by-play</h3>
            <PlayByPlay events={events} home={home} />
          </div>
        </div>
        {view !== "real" && (
          <div className="grid gap-6 xl:grid-cols-2">
            <BoxTable code={home} rows={scenario.box[0]} />
            <BoxTable code={away} rows={scenario.box[1]} />
          </div>
        )}
        <div className="grid max-w-3xl grid-cols-2 gap-4">
          <ShotMap events={events} code={home} color="var(--side-a)" />
          <ShotMap events={events} code={away} color="var(--side-b)" />
        </div>
        <p className="text-xs text-dim">Daireler isabet, çarpılar kaçan şut. Simüle edilen şutların yeri, oyuncunun aynı bölgeden gerçek şutlarından seçilir.</p>
      </section>

      <section className="space-y-5">
        <h2 className="display t-sec">Neden böyle bekleniyor?</h2>
        <p className="max-w-[75ch] text-muted">Beklenen fark şu dört yerden geliyor. Altında, kartlarındaki puanlarıyla bu farkı taşıyan oyuncular var.</p>
        <div className="max-w-4xl"><Edges edges={r.edges} home={home} away={away} /></div>
        <div className="grid gap-6 xl:grid-cols-2">
          <PlayerExpect rows={r.players[home]} code={home} />
          <PlayerExpect rows={r.players[away]} code={away} />
        </div>
        <p className="text-xs text-dim">Ortalama ve %80 aralık. Oyuncu rakamları, puanlarla aynı verilerden gelir; puanın kendisi değil arkasındaki oranlar kullanılır.</p>
        {r.other_side.rows.length > 0 && (
          <div>
            <h3 className="display t-sub mb-2">{r.other_side.team} kazandığında ne değişiyor?</h3>
            <p className="mb-2 max-w-[70ch] text-sm text-muted">{r.other_side.team} kazandığı maçlarla kaybettiği maçların karşılaştırması. Fark, çoğunlukla şut isabetinde.</p>
            <table className="text-sm">
              <thead>
                <tr className="text-left text-xs text-muted">
                  <th scope="col" className="py-1 pr-6 font-semibold"><span className="sr-only">Ölçüm</span></th>
                  <th scope="col" className="px-2 text-right font-semibold">Kazandığında</th>
                  <th scope="col" className="px-2 text-right font-semibold">Kaybettiğinde</th>
                </tr>
              </thead>
              <tbody>
                {r.other_side.rows.map((row) => (
                  <tr key={row.label} className="border-t border-line">
                    <th scope="row" lang="en" className="py-1 pr-6 text-left font-medium">{row.label}</th>
                    <td className="num px-2 text-right font-semibold">{row.upset}</td>
                    <td className="num px-2 text-right text-muted">{row.usual}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {r.coach && (
        <section className="space-y-3">
          <h2 className="display t-sec">Koç notları</h2>
          <p className="max-w-[75ch] text-muted">Her takım için maçın en çok neye bağlı olduğu: maç, tek bir şey değiştirilerek yeniden oynatıldı. Bu, ne kadar değerli olduğunu söyler; nasıl yapılacağını söylemez, çünkü set ve savunma eşleşmesi verisi yok.</p>
          <Coach notes={r.coach} />
        </section>
      )}

      {c && r.real && (
        <section className="space-y-6">
          <h2 className="display t-sec">Gerçekle karşılaştırma</h2>
          <p className="max-w-[75ch] text-muted">
            Tek bir simülasyon gerçek maçı olay olay tekrar edemez: bir hücumun sonucunun çoğu şanstır. Burada aranan şey, olanın beklenen aralıkta olup olmadığı ve farkın nereden geldiğidir.
          </p>
          <div>
            <h3 className="display t-sub mb-2">Fark nereden geldi?</h3>
            <ul className="max-w-[75ch] space-y-1 text-sm">
              {c.gaps.slice(0, 5).map((g, i) => <li key={i}>{gapSentence(g)}</li>)}
            </ul>
          </div>
          <CompareTable c={c} home={home} away={away} />
          <div className="grid gap-6 xl:grid-cols-2">
            <PlayersCompare rows={r.players[home]} code={home} />
            <PlayersCompare rows={r.players[away]} code={away} />
          </div>
          <p className="text-xs text-dim">Her hücrede gerçek değer ve %80 beklenen aralık. Değişiklik sayısı gerçekte {c.subs[0]} ve {c.subs[1]}.{c.missing_players > 0 ? ` Tahmin edilen kadroda olmayıp süre alan oyuncu: ${c.missing_players}.` : ""}</p>
          <div>
            <h3 className="display t-sub mb-3">Olay olay: gerçek maç ve en olası senaryo</h3>
            <SideBySide left={r.real.events} right={r.typical.events} leftLabel="Gerçek maç" rightLabel="En olası senaryo" home={home} />
          </div>
          <p className="text-xs text-dim">Senaryoda sayı, top kaybı ve faul oyuncuların oranlarından çıkar. Kimin kimi savunduğu, perdeler ve set çeşitleri veride yok.</p>
        </section>
      )}
    </div>
  );
}
