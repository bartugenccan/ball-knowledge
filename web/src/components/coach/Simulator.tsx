"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { PossessionFlow } from "@/components/coach/PossessionFlow";
import { FlipButton } from "@/components/Flip";
import { Flap } from "@/components/motion/Flap";
import { InView } from "@/components/motion/InView";
import { Odo } from "@/components/motion/Odo";
import { PlayBoard } from "@/components/PlayBoard";
import { clubVars } from "@/lib/clubs";
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
  const two = take((p) => 2 * num(p, "three_point") + num(p, "free_throw"));
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
  const resultsRef = useRef<HTMLElement>(null);

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
      // on smaller screens the button sits far below the top of the results
      requestAnimationFrame(() => {
        const el = resultsRef.current;
        if (!el) return;
        const top = el.getBoundingClientRect().top;
        if (top < 64 || top > window.innerHeight * 0.5) {
          el.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
        }
      });
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
    <div className="grid gap-x-10 gap-y-8 lg:grid-cols-[minmax(0,21rem)_minmax(0,1fr)]">
      <aside className="space-y-8">
        <section className="space-y-3">
          <h2 className="display t-sub border-b-2 border-ink pb-2">Set</h2>
          <div className="flex flex-wrap gap-x-4" role="tablist" aria-label="Set">
            {sets.map((s) => (
              <button key={s.id} type="button" role="tab" aria-selected={setId === s.id} className="tab"
                onClick={() => {
                  setSetId(s.id);
                  setSetJson(JSON.stringify(s, null, 2));
                  setResult(null);
                }}>
                {s.name}
              </button>
            ))}
          </div>
          <p className="text-sm text-muted">{sets.find((s) => s.id === setId)?.description}</p>
          <details className="text-xs">
            <summary className="cursor-pointer font-semibold text-muted hover:text-ink">Seti düzenle (JSON)</summary>
            <textarea value={setJson} onChange={(e) => setSetJson(e.target.value)} spellCheck={false} aria-label="Set JSON"
              className="mt-2 h-64 w-full border-2 border-ink bg-panel p-3 font-mono text-[11px] text-ink focus:border-accent focus:outline-none" />
            {!parsedSet && <p className="r-poor">JSON geçersiz.</p>}
          </details>
        </section>

        {(["off", "def"] as const).map((side) => {
          const team = side === "off" ? offTeam : defTeam;
          const assign = side === "off" ? offense : defense;
          return (
            <section key={side} className="space-y-3">
              <h2 className="display t-sub border-b-2 border-ink pb-2">{side === "off" ? "Hücum" : "Savunma"}</h2>
              <select value={team?.code ?? ""} onChange={(e) => loadTeam(e.target.value, side)} className="field w-full text-sm font-semibold"
                aria-label={side === "off" ? "Hücum takımı" : "Savunma takımı"}>
                <option value="">Takım seçin</option>
                {teams.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
              </select>
              <AnimatePresence initial={false}>
                {team && (
                  <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.35, ease: EASE }} className="space-y-1.5 overflow-hidden">
                    {SLOTS.map((s) => (
                      <label key={s} className="flex items-center gap-2 text-xs">
                        <span className="num grid h-7 w-7 shrink-0 place-items-center bg-ink text-sm text-bg">{s}</span>
                        <span className="w-20 shrink-0 text-muted">{side === "off" ? SLOT_LABEL[s] : `${s}'i savunan`}</span>
                        <select value={assign[s] ?? ""}
                          onChange={(e) => {
                            (side === "off" ? setOffense : setDefense)((prev) => ({ ...prev, [s]: e.target.value }));
                            setResult(null);
                          }}
                          className="field min-w-0 flex-1 !py-1">
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

        <section className="space-y-4 text-sm">
          <h2 className="display t-sub border-b-2 border-ink pb-2">Durum</h2>
          <label className="block space-y-1.5">
            <span className="flex items-baseline justify-between text-xs text-muted">
              <span>Beşli kaç dakikadır sahada</span>
              <span className="num text-lg text-ink">{stint} dk</span>
            </span>
            <input type="range" min={0} max={12} step={1} value={stint} onChange={(e) => setStint(Number(e.target.value))} className="slider" />
          </label>
          <label className="flex cursor-pointer items-center gap-3 text-xs">
            <input type="checkbox" checked={clutch} onChange={(e) => setClutch(e.target.checked)} className="sr-only" />
            <span className="tgl" aria-hidden />
            Clutch: son 5 dakika, fark 5 sayı veya daha az
          </label>
          <FlipButton type="button" onClick={run} disabled={!ready || busy} className="w-full !text-base">
            {busy ? "Oynatılıyor" : "10.000 kez oynat"}
          </FlipButton>
          {!ready && !busy && <p className="text-xs text-muted">Oynatmak için iki takımı da seçin.</p>}
        </section>
      </aside>

      <section ref={resultsRef} className="club scroll-target min-w-0 space-y-10" style={clubVars(offTeam?.code)}>
        {error && <p className="border-l-4 border-accent bg-bg-2 p-4 text-sm font-medium">{error}</p>}
        {!result && !error && (
          <div className="bg-board p-6 text-chalk md:p-8">
            <p className="display t-sub !text-2xl">Hücum ve savunmayı seçin</p>
            <p className="mb-4 mt-2 text-sm text-chalk-2">Takımları seçince beşliler puanlara göre yerleşir, istersen değiştirebilirsin.</p>
            <PlayBoard />
          </div>
        )}
        {result && parsedSet && (
          <Results runId={runId} result={result} set={parsedSet} leaguePPP={leaguePPP} nameOf={nameOf} />
        )}
      </section>
    </div>
  );
}

function Results({ runId, result, set, leaguePPP, nameOf }: {
  runId: number;
  result: SimResult;
  set: SetDef;
  leaguePPP?: number;
  nameOf: (side: "off" | "def", slot: string) => string;
}) {
  const diff = leaguePPP ? result.ppp - leaguePPP : 0;
  const maxSens = Math.max(0.01, ...(result.sensitivity ?? []).map((s) => Math.abs(s.ppp_contribution)));
  const hot = diff >= 0;
  return (
    <>
      <div className="grid items-end gap-x-10 gap-y-6 sm:grid-cols-[auto_1fr_1fr]">
        <div>
          <p className="mb-2 text-sm text-muted">Possession başına sayı</p>
          <Flap value={result.ppp} decimals={2} size="clamp(3.5rem, 7vw, 5.5rem)"
            bg={hot ? "var(--club)" : "var(--muted)"} ink={hot ? "var(--club-ink)" : "var(--bg)"} />
          {leaguePPP && (
            <p className="mt-2 text-sm">
              <span className={`font-bold ${hot ? "r-elite" : "r-poor"}`}>{hot ? "+" : ""}{diff.toFixed(2)}</span>
              <span className="text-muted"> lig ortalamasına göre ({leaguePPP.toFixed(2)})</span>
            </p>
          )}
        </div>
        <Stat key={`t${runId}`} label="Top kaybı" value={100 * result.turnover_rate} />
        <Stat key={`z${runId}`} label="Sayısız biten" value={100 * (result.points_distribution["0"] ?? 0)} />
      </div>

      <section className="rule-t pt-4">
        <h3 className="display t-sub mb-1">Possession akışı</h3>
        <p className="mb-4 text-xs text-muted">Bant kalınlığı o dala giden possession payı. Kulüp rengi ligden iyi, gri kötü bir sonuç demek.</p>
        <PossessionFlow key={runId} set={set} result={result} league={leaguePPP ?? 1.1} nameOf={(slot) => nameOf("off", slot)} />
      </section>

      <section className="overflow-x-auto">
        <table className="ledger w-full text-sm">
          <thead>
            <tr className="text-left">
              <th className="py-2 pr-2">ŞUT</th>
              <th className="px-2 py-2 text-right">ULAŞMA</th>
              <th className="px-2 py-2 text-right">CONTEST</th>
              <th className="px-2 py-2 text-right">BOŞSA</th>
              <th className="px-2 py-2 text-right">CONTEST&apos;TE</th>
              <th className="px-2 py-2 text-right">FAUL</th>
              <th className="py-2 pl-2 text-right">PPP</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(result.shots)
              .sort((a, b) => b[1].reach_rate - a[1].reach_rate)
              .map(([id, s]) => {
                const node = set.nodes[id];
                return (
                  <tr key={id}>
                    <td className="py-2 pr-2">
                      <div className="font-semibold">{nameOf("off", node.shooter ?? "")}</div>
                      <div className="text-xs text-muted">
                        {ZONE_LABEL[s.zone]}, {node.creation === "dribble" ? "top sürerek" : "catch & shoot"}, savunan {nameOf("def", node.defender ?? node.shooter ?? "")}
                      </div>
                    </td>
                    <td className="px-2 py-2 text-right">{pct(s.reach_rate, 0)}</td>
                    <td className="px-2 py-2 text-right">{pct(s.p_contest, 0)}</td>
                    <td className="px-2 py-2 text-right font-semibold r-elite">{pct(s.p_make_open, 0)}</td>
                    <td className="px-2 py-2 text-right font-semibold r-low">{pct(s.p_make_contested, 0)}</td>
                    <td className="px-2 py-2 text-right">{pct(s.p_foul, 0)}</td>
                    <td className="py-2 pl-2 text-right num text-lg">{s.ppp_when_reached?.toFixed(2) ?? "-"}</td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </section>

      {result.sensitivity && (
        <section className="rule-t pt-4">
          <h3 className="display t-sub">Oyuncu katkısı</h3>
          <p className="mb-4 mt-1 text-xs text-muted">Oyuncunun yerine lig ortalaması bir oyuncu koysaydın PPP ne kadar değişirdi.</p>
          <InView key={runId} amount={0.2}>
            <ul className="space-y-2 text-sm">
              {result.sensitivity.map((s, i) => {
                const w = Math.abs(s.ppp_contribution) / maxSens / 2;
                const pos = s.ppp_contribution >= 0;
                return (
                  <li key={s.slot} className="grid grid-cols-[minmax(7rem,12rem)_1fr_3.5rem] items-center gap-3">
                    <span className="truncate"><span className="num mr-1 text-accent-text">{s.slot}</span> {properName(s.player)}</span>
                    <div className="relative h-5">
                      <span className="absolute inset-y-0 left-1/2 w-[2px] -translate-x-1/2 bg-ink" />
                      <span className={`grow-bar absolute inset-y-0.5 ${pos ? "left-1/2 heat-r-elite" : "right-1/2 heat-r-poor"}`}
                        style={{ width: `${w * 100}%`, ["--o" as string]: pos ? "left" : "right", ["--i" as string]: i * 3 }} />
                    </div>
                    <span className={`text-right text-xs font-semibold ${pos ? "r-elite" : "r-poor"}`}>{pos ? "+" : ""}{s.ppp_contribution.toFixed(3)}</span>
                  </li>
                );
              })}
            </ul>
          </InView>
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
    <div>
      <p className="mb-1 text-sm text-muted">{label}</p>
      <Odo value={value} decimals={1} suffix="%" className="num text-5xl" />
    </div>
  );
}
