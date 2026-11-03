"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { CountUp } from "@/components/motion/CountUp";
import { pct, properName, ZONE_LABEL } from "@/lib/format";
import type { Meta, RosterRow, SetDef, SimResult, TeamSummary } from "@/lib/types";

const SLOTS = ["1", "2", "3", "4", "5"] as const;
const SLOT_LABEL: Record<string, string> = { "1": "Oyun kurucu", "2": "Şutör", "3": "Kanat", "4": "Uzun forvet", "5": "Pivot" };
const EASE = [0.16, 1, 0.3, 1] as const;

type Roster = { code: string; name: string; roster: RosterRow[] };

async function getJSON<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `HTTP ${r.status}`);
  return r.json();
}

/** Default slot guess from ratings: 5 = best big, 4 = next big, 1 = best passer, 2 = best shooter, 3 = rest. */
function guessSlots(roster: RosterRow[]): Record<string, string> {
  const pool = roster.filter((p) => p.qualified).slice(0, 8);
  const num = (p: RosterRow, k: string) => Number(p[k]);
  const take = (score: (p: RosterRow) => number) => {
    pool.sort((a, b) => score(b) - score(a));
    return pool.shift()!.player_id;
  };
  if (pool.length < 5) return Object.fromEntries(SLOTS.map((s, i) => [s, roster[i]?.player_id ?? ""]));
  const five = take((p) => num(p, "def_rebounding") + num(p, "shot_blocking") + num(p, "finishing"));
  const four = take((p) => num(p, "def_rebounding") + num(p, "off_rebounding"));
  const one = take((p) => 2 * num(p, "passing") + num(p, "ball_security"));
  const two = take((p) => 2 * num(p, "three_point") + num(p, "corner_three"));
  const three = take((p) => Number(p.minutes));
  return { "1": one, "2": two, "3": three, "4": four, "5": five };
}

export function Simulator() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [sets, setSets] = useState<SetDef[]>([]);
  const [teams, setTeams] = useState<TeamSummary[]>([]);
  const [setId, setSetId] = useState<string>("");
  const [setJson, setSetJson] = useState<string>("");
  const [offTeam, setOffTeam] = useState<Roster | null>(null);
  const [defTeam, setDefTeam] = useState<Roster | null>(null);
  const [offense, setOffense] = useState<Record<string, string>>({});
  const [defense, setDefense] = useState<Record<string, string>>({});
  const [stint, setStint] = useState(4);
  const [clutch, setClutch] = useState(false);
  const [result, setResult] = useState<SimResult | null>(null);
  const [runId, setRunId] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([getJSON<Meta>("/api/meta"), getJSON<{ sets: SetDef[] }>("/api/sets"), getJSON<{ teams: TeamSummary[] }>("/api/teams")])
      .then(([m, s, t]) => {
        setMeta(m);
        setSets(s.sets);
        setTeams(t.teams);
        if (s.sets[0]) {
          setSetId(s.sets[0].id);
          setSetJson(JSON.stringify(s.sets[0], null, 2));
        }
      })
      .catch((e) => setError(`API'ye ulaşılamadı: ${e.message}`));
  }, []);

  async function loadTeam(code: string, side: "off" | "def") {
    if (!code) return;
    const t = await getJSON<Roster>(`/api/teams/${code}`);
    const slots = guessSlots(t.roster);
    if (side === "off") {
      setOffTeam(t);
      setOffense(slots);
    } else {
      setDefTeam(t);
      setDefense(slots);
    }
    setResult(null);
  }

  const parsedSet = useMemo<SetDef | null>(() => {
    try {
      return JSON.parse(setJson) as SetDef;
    } catch {
      return null;
    }
  }, [setJson]);

  const ready = Boolean(parsedSet && SLOTS.every((s) => offense[s] && defense[s]));

  async function run() {
    if (!ready) return;
    setBusy(true);
    setError(null);
    try {
      const r = await getJSON<SimResult>("/api/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ set: parsedSet, offense, defense, context: { stint_minutes: stint, clutch }, iterations: 10000 }),
      });
      setResult(r);
      setRunId((n) => n + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const nameOf = (side: "off" | "def", slot: string) => {
    const t = side === "off" ? offTeam : defTeam;
    const id = (side === "off" ? offense : defense)[slot];
    const p = t?.roster.find((r) => r.player_id === id);
    return p ? properName(String(p.player)) : slot;
  };
  const leaguePPP = meta ? meta.league_ppp[meta.latest] : undefined;

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,23rem)_1fr]">
      <aside className="space-y-4">
        <section className="panel space-y-3 p-4">
          <h2 className="font-display text-lg font-bold uppercase tracking-wide">Set</h2>
          <div className="flex flex-wrap gap-1.5">
            {sets.map((s) => (
              <button key={s.id} type="button"
                onClick={() => {
                  setSetId(s.id);
                  setSetJson(JSON.stringify(s, null, 2));
                  setResult(null);
                }}
                className={`pill px-3 py-1.5 text-sm ${setId === s.id ? "bg-accent text-accent-ink" : "border border-line-2 text-muted hover:text-ink"}`}>
                {s.name}
              </button>
            ))}
          </div>
          <p className="text-sm text-muted">{sets.find((s) => s.id === setId)?.description}</p>
          <details className="text-xs">
            <summary className="cursor-pointer text-dim hover:text-muted">Seti düzenle (JSON)</summary>
            <textarea value={setJson} onChange={(e) => setSetJson(e.target.value)} spellCheck={false}
              className="mt-2 h-64 w-full rounded-xl border border-line-2 bg-bg-2 p-3 font-mono text-[11px] text-ink focus:border-accent focus:outline-none" />
            {!parsedSet && <p className="r-poor">JSON geçersiz.</p>}
          </details>
        </section>

        {(["off", "def"] as const).map((side) => {
          const team = side === "off" ? offTeam : defTeam;
          const assign = side === "off" ? offense : defense;
          return (
            <section key={side} className="panel space-y-3 p-4">
              <h2 className="font-display text-lg font-bold uppercase tracking-wide">{side === "off" ? "Hücum" : "Savunma"}</h2>
              <select value={team?.code ?? ""} onChange={(e) => loadTeam(e.target.value, side)} className="field w-full px-3 py-2 text-sm"
                aria-label={side === "off" ? "Hücum takımı" : "Savunma takımı"}>
                <option value="">Takım seçin</option>
                {teams.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
              </select>
              <AnimatePresence initial={false}>
                {team && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.35, ease: EASE }} className="space-y-2 overflow-hidden">
                    {SLOTS.map((s) => (
                      <label key={s} className="flex items-center gap-2 text-xs">
                        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-panel-2 font-display text-sm font-bold text-accent">{s}</span>
                        <span className="w-20 shrink-0 text-muted">{side === "off" ? SLOT_LABEL[s] : `${s}'i savunan`}</span>
                        <select value={assign[s] ?? ""}
                          onChange={(e) => {
                            (side === "off" ? setOffense : setDefense)((prev) => ({ ...prev, [s]: e.target.value }));
                            setResult(null);
                          }}
                          className="field min-w-0 flex-1 px-2.5 py-1.5">
                          {team.roster.map((p) => <option key={p.player_id} value={p.player_id}>{properName(String(p.player))}</option>)}
                        </select>
                      </label>
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>
            </section>
          );
        })}

        <section className="panel space-y-4 p-4 text-sm">
          <h2 className="font-display text-lg font-bold uppercase tracking-wide">Durum</h2>
          <label className="block space-y-2">
            <span className="flex justify-between text-xs text-muted">
              <span>Beşli kaç dakikadır sahada</span>
              <span className="font-mono text-ink">{stint} dk</span>
            </span>
            <input type="range" min={0} max={12} step={1} value={stint} onChange={(e) => setStint(Number(e.target.value))}
              className="w-full accent-[var(--accent)]" />
          </label>
          <label className="flex cursor-pointer items-center gap-3 text-xs">
            <input type="checkbox" checked={clutch} onChange={(e) => setClutch(e.target.checked)} className="peer sr-only" />
            <span className="relative h-5 w-9 rounded-full bg-line-2 transition-colors peer-checked:bg-accent peer-focus-visible:ring-2 peer-focus-visible:ring-accent after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-ink after:transition-transform peer-checked:after:translate-x-4" />
            Clutch: son 5 dakika, fark 5 sayı veya daha az
          </label>
          <motion.button type="button" onClick={run} disabled={!ready || busy} whileTap={{ scale: 0.97 }}
            className="btn-accent relative w-full overflow-hidden px-4 py-3 disabled:cursor-not-allowed disabled:opacity-40">
            {busy && (
              <motion.span aria-hidden className="absolute inset-y-0 left-0 w-1/3 bg-white/25"
                animate={{ x: ["-100%", "300%"] }} transition={{ repeat: Infinity, duration: 1.1, ease: "easeInOut" }} />
            )}
            <span className="relative">{busy ? "Oynatılıyor" : "10.000 kez oynat"}</span>
          </motion.button>
        </section>
      </aside>

      <section className="min-w-0 space-y-4">
        {error && <p className="panel p-4 text-sm r-poor">{error}</p>}
        {!result && !error && (
          <div className="panel grid min-h-80 place-items-center p-8 text-center">
            <div className="space-y-2">
              <p className="font-display text-2xl font-bold uppercase">Hücum ve savunmayı seçin</p>
              <p className="text-sm text-muted">Takımları seçince beşliler puanlara göre yerleşir, istersen değiştirebilirsin.</p>
            </div>
          </div>
        )}
        <AnimatePresence mode="wait">
          {result && parsedSet && (
            <motion.div key={runId} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.45, ease: EASE }} className="space-y-4">
              <Results result={result} set={parsedSet} leaguePPP={leaguePPP} nameOf={nameOf} />
            </motion.div>
          )}
        </AnimatePresence>
      </section>
    </div>
  );
}

function Results({ result, set, leaguePPP, nameOf }: {
  result: SimResult;
  set: SetDef;
  leaguePPP?: number;
  nameOf: (side: "off" | "def", slot: string) => string;
}) {
  const diff = leaguePPP ? result.ppp - leaguePPP : 0;
  const maxSens = Math.max(0.01, ...(result.sensitivity ?? []).map((s) => Math.abs(s.ppp_contribution)));
  return (
    <>
      <div className="grid gap-4 sm:grid-cols-[1.4fr_1fr_1fr]">
        <div className="panel overflow-hidden p-5">
          <div aria-hidden className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-accent/25 blur-3xl" />
          <p className="relative text-sm text-muted">Possession başına sayı</p>
          <CountUp value={result.ppp} decimals={2} className="relative font-display text-7xl font-extrabold leading-none" />
          {leaguePPP && (
            <p className="relative mt-1 text-sm">
              <span className={diff >= 0 ? "r-elite" : "r-poor"}>{diff >= 0 ? "+" : ""}{diff.toFixed(2)}</span>
              <span className="text-dim"> lig ortalamasına göre ({leaguePPP.toFixed(2)})</span>
            </p>
          )}
        </div>
        <Stat label="Top kaybı" value={100 * result.turnover_rate} />
        <Stat label="Sayısız biten" value={100 * (result.points_distribution["0"] ?? 0)} />
      </div>

      <section className="panel p-5">
        <h3 className="mb-4 font-display text-lg font-bold uppercase tracking-wide">Dallanma</h3>
        <ol className="space-y-5 text-sm">
          {Object.entries(result.actions).map(([id, a], ai) => (
            <li key={id}>
              <div className="mb-2 flex items-baseline justify-between gap-2">
                <span className="font-medium">{a.label}</span>
                <span className="text-xs text-dim">top kaybı riski {pct(a.turnover_prob)}</span>
              </div>
              <ul className="space-y-1.5">
                {a.options.map((o, oi) => {
                  const label = set.nodes[id]?.options?.find((x) => x.to === o.to)?.label ?? set.nodes[o.to]?.label ?? o.to;
                  return (
                    <li key={o.to} className="grid grid-cols-[3rem_1fr] items-center gap-3">
                      <span className="text-right font-mono text-xs">{pct(o.prob, 0)}</span>
                      <div className="relative h-7 overflow-hidden rounded-lg bg-bg-2">
                        <motion.div className="absolute inset-y-0 left-0 w-full origin-left rounded-lg bg-[var(--accent-soft)] ring-1 ring-inset ring-accent/40"
                          initial={{ scaleX: 0 }} animate={{ scaleX: o.prob }}
                          transition={{ duration: 0.7, delay: ai * 0.12 + oi * 0.06, ease: EASE }} />
                        <span className="relative flex h-full items-center truncate px-2.5 text-xs">{label}</span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel overflow-x-auto">
        <table className="data-table w-full text-sm">
          <thead>
            <tr className="text-left">
              <th className="px-4 py-3">ŞUT</th>
              <th className="px-2 py-3 text-right">ULAŞMA</th>
              <th className="px-2 py-3 text-right">CONTEST</th>
              <th className="px-2 py-3 text-right">BOŞSA</th>
              <th className="px-2 py-3 text-right">CONTEST&apos;TE</th>
              <th className="px-2 py-3 text-right">FAUL</th>
              <th className="px-4 py-3 text-right">PPP</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(result.shots)
              .sort((a, b) => b[1].reach_rate - a[1].reach_rate)
              .map(([id, s], i) => {
                const node = set.nodes[id];
                return (
                  <tr key={id} className="rise border-t border-line/60" style={{ ["--i" as string]: i }}>
                    <td className="px-4 py-2.5">
                      <div className="font-medium">{nameOf("off", node.shooter ?? "")}</div>
                      <div className="text-xs text-dim">
                        {ZONE_LABEL[s.zone]}, {node.creation === "dribble" ? "top sürerek" : "catch & shoot"}, savunan {nameOf("def", node.defender ?? node.shooter ?? "")}
                      </div>
                    </td>
                    <td className="px-2 py-2.5 text-right">{pct(s.reach_rate, 0)}</td>
                    <td className="px-2 py-2.5 text-right">{pct(s.p_contest, 0)}</td>
                    <td className="px-2 py-2.5 text-right r-elite">{pct(s.p_make_open, 0)}</td>
                    <td className="px-2 py-2.5 text-right r-low">{pct(s.p_make_contested, 0)}</td>
                    <td className="px-2 py-2.5 text-right">{pct(s.p_foul, 0)}</td>
                    <td className="px-4 py-2.5 text-right font-display text-lg font-bold">{s.ppp_when_reached?.toFixed(2) ?? "-"}</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </section>

      {result.sensitivity && (
        <section className="panel p-5">
          <h3 className="font-display text-lg font-bold uppercase tracking-wide">Oyuncu katkısı</h3>
          <p className="mb-4 text-xs text-dim">Oyuncunun yerine lig ortalaması bir oyuncu koysaydın PPP ne kadar değişirdi.</p>
          <ul className="space-y-2 text-sm">
            {result.sensitivity.map((s, i) => {
              const w = Math.abs(s.ppp_contribution) / maxSens / 2;
              const pos = s.ppp_contribution >= 0;
              return (
                <li key={s.slot} className="grid grid-cols-[minmax(8rem,12rem)_1fr_4rem] items-center gap-3">
                  <span className="truncate"><span className="font-display font-bold text-accent">{s.slot}</span> {properName(s.player)}</span>
                  <div className="relative h-2 rounded-full bg-bg-2">
                    <span className="absolute inset-y-0 left-1/2 w-px bg-line-2" />
                    <motion.span className={`absolute inset-y-0 rounded-full ${pos ? "left-1/2 origin-left fill-r-elite" : "right-1/2 origin-right fill-r-poor"}`}
                      style={{ width: `${w * 100}%` }}
                      initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 0.6, delay: 0.2 + i * 0.07, ease: EASE }} />
                  </div>
                  <span className={`text-right font-mono text-xs ${pos ? "r-elite" : "r-poor"}`}>{pos ? "+" : ""}{s.ppp_contribution.toFixed(3)}</span>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <p className="text-xs text-dim">
        Veriden kalibre edilenler: {result.params.calibrated.join(", ") || "yok, varsayılan değerler"}. Boş ve contest edilmiş şut farkı ile
        top sürerek şut cezası önsel değerdir (NBA takip verisi). Topsuz savunma puanları tahminidir.
      </p>
    </>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="panel p-5">
      <p className="text-sm text-muted">{label}</p>
      <CountUp value={value} decimals={1} suffix="%" className="font-display text-5xl font-extrabold leading-none" />
    </div>
  );
}
