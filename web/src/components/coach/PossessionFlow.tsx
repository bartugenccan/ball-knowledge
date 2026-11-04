"use client";

import { useReducedMotion } from "motion/react";
import { useMemo } from "react";
import { InView } from "@/components/motion/InView";
import type { SetDef, SimResult } from "@/lib/types";

const W = 1000;
const PX_PER_ONE = 340; // height of 100% of possessions
const GAP = 40;
const BAR = 14;
const TO = "__turnover";

type FlowNode = { id: string; depth: number; reach: number; y: number; h: number; kind: "action" | "shot" | "turnover" };
type FlowLink = { from: string; to: string; flow: number; path: string; center: string; width: number; dot: number };

function heat(ppp: number | null | undefined, league: number) {
  if (ppp == null) return "var(--heat-avg)";
  const d = ppp - league;
  if (d >= 0.15) return "var(--heat-elite)";
  if (d >= 0) return "var(--heat-good)";
  if (d >= -0.15) return "var(--heat-avg)";
  if (d >= -0.35) return "var(--heat-low)";
  return "var(--heat-poor)";
}

/** Walks the set graph once: how many of the possessions reach each node, and by which edge. */
function layout(set: SetDef, result: SimResult) {
  const reach = new Map<string, number>([[set.start, 1]]);
  const depth = new Map<string, number>([[set.start, 0]]);
  const edges: { from: string; to: string; flow: number }[] = [];
  let turnovers = 0;

  // Topological order (depth-first). A hand-edited set with a cycle simply stops at the repeat.
  const order: string[] = [];
  const seen = new Set<string>();
  const visit = (id: string) => {
    if (seen.has(id) || !set.nodes[id]) return;
    seen.add(id);
    for (const o of result.actions[id]?.options ?? []) visit(o.to);
    order.unshift(id);
  };
  visit(set.start);

  for (const id of order) {
    const a = result.actions[id];
    if (!a) continue;
    const here = reach.get(id) ?? 0;
    const lost = here * a.turnover_prob;
    turnovers += lost;
    for (const o of a.options) {
      const flow = (here - lost) * o.prob;
      reach.set(o.to, (reach.get(o.to) ?? 0) + flow);
      depth.set(o.to, Math.max(depth.get(o.to) ?? 0, (depth.get(id) ?? 0) + 1));
      edges.push({ from: id, to: o.to, flow });
    }
    if (lost > 0) edges.push({ from: id, to: TO, flow: lost });
  }

  const maxDepth = Math.max(1, ...[...depth.values()]);
  depth.set(TO, maxDepth);
  reach.set(TO, turnovers);

  const nodes: FlowNode[] = [...order, TO].map((id) => ({
    id,
    depth: depth.get(id) ?? 0,
    reach: reach.get(id) ?? 0,
    y: 0,
    h: Math.max(5, (reach.get(id) ?? 0) * PX_PER_ONE),
    kind: id === TO ? "turnover" : result.actions[id] ? "action" : "shot",
  }));

  const columns = new Map<number, FlowNode[]>();
  for (const n of nodes) columns.set(n.depth, [...(columns.get(n.depth) ?? []), n]);
  const colHeight = (c: FlowNode[]) => c.reduce((sum, n) => sum + n.h, 0) + GAP * (c.length - 1);
  const H = Math.max(...[...columns.values()].map(colHeight)) + 44;
  const center = new Map<string, number>();
  // left to right: sit each node near the possessions feeding it, turnovers always at the bottom
  for (const d of [...columns.keys()].sort((p, q) => p - q)) {
    const col = columns.get(d)!;
    const pull = (n: FlowNode) => {
      if (n.id === TO) return Infinity;
      const inc = edges.filter((e) => e.to === n.id);
      const total = inc.reduce((sum, e) => sum + e.flow, 0) || 1;
      return inc.reduce((sum, e) => sum + (center.get(e.from) ?? 0) * e.flow, 0) / total;
    };
    col.sort((p, q) => pull(p) - pull(q));
    let y = (H - colHeight(col)) / 2;
    for (const n of col) {
      n.y = y;
      center.set(n.id, y + n.h / 2);
      y += n.h + GAP;
    }
  }

  const byId = new Map(nodes.map((n) => [n.id, n]));
  // labels sit right of each bar, so reserve the last stretch of width for them
  const x = (d: number) => 6 + (d / maxDepth) * (W - 250);
  const known = edges.filter((e) => byId.has(e.from) && byId.has(e.to));
  const width = (e: (typeof known)[number]) => Math.max(1.5, e.flow * PX_PER_ONE);
  // bands leave a node in the order of their targets and enter in the order of their sources
  const y0Of = new Map<(typeof known)[number], number>();
  const y1Of = new Map<(typeof known)[number], number>();
  const outY = new Map<string, number>();
  for (const e of [...known].sort((p, q) => center.get(p.to)! - center.get(q.to)!)) {
    const at = outY.get(e.from) ?? byId.get(e.from)!.y;
    y0Of.set(e, at + width(e) / 2);
    outY.set(e.from, at + width(e));
  }
  const inY = new Map<string, number>();
  for (const e of [...known].sort((p, q) => center.get(p.from)! - center.get(q.from)!)) {
    const at = inY.get(e.to) ?? byId.get(e.to)!.y;
    y1Of.set(e, at + width(e) / 2);
    inY.set(e.to, at + width(e));
  }
  const links: FlowLink[] = known.map((e) => {
    const a = byId.get(e.from)!;
    const b = byId.get(e.to)!;
    const w = width(e);
    const y0 = y0Of.get(e)!;
    const y1 = y1Of.get(e)!;
    const x0 = x(a.depth) + BAR;
    const x1 = x(b.depth);
    const mid = (x0 + x1) / 2;
    return {
      from: e.from,
      to: e.to,
      flow: e.flow,
      width: w,
      dot: a.depth,
      center: `M${x0} ${y0}C${mid} ${y0} ${mid} ${y1} ${x1} ${y1}`,
      path: `M${x0} ${y0 - w / 2}C${mid} ${y0 - w / 2} ${mid} ${y1 - w / 2} ${x1} ${y1 - w / 2}L${x1} ${y1 + w / 2}C${mid} ${y1 + w / 2} ${mid} ${y0 + w / 2} ${x0} ${y0 + w / 2}Z`,
    };
  });
  return { nodes, links, H, x };
}

/**
 * The set as a river of possessions. Band width is the share of possessions on that branch;
 * bands that end in a good shot wear the club's colour, bad ones go grey. Particles run through the river once
 * per simulation, so you see the 10,000 trips being played.
 */
export function PossessionFlow({
  set,
  result,
  league,
  nameOf,
}: {
  set: SetDef;
  result: SimResult;
  league: number;
  nameOf: (slot: string) => string;
}) {
  const reduce = useReducedMotion();
  const { nodes, links, H, x } = useMemo(() => layout(set, result), [set, result]);

  const colorOf = (id: string) => (id === TO ? "var(--heat-poor)" : result.shots[id] ? heat(result.shots[id].ppp_when_reached, league) : "var(--ink)");

  // best branch colour for an action node's incoming band: the mean PPP downstream
  const downstream = new Map<string, number>();
  const pppOf = (id: string): number => {
    if (id === TO) return 0;
    const s = result.shots[id];
    if (s) return s.ppp_when_reached ?? 0;
    if (downstream.has(id)) return downstream.get(id)!;
    downstream.set(id, 0); // a hand-edited set may contain a cycle: stop instead of recursing forever
    const a = result.actions[id];
    const v = a ? a.options.reduce((sum, o) => sum + o.prob * pppOf(o.to), 0) : 0;
    downstream.set(id, v);
    return v;
  };

  return (
    <InView amount={0.15}>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${W} ${H}`} className="block w-full min-w-[720px]" role="img"
          aria-label={`Set akışı: ${nodes.filter((n) => n.kind === "shot").map((n) => `${set.nodes[n.id]?.label ?? n.id} yüzde ${(n.reach * 100).toFixed(0)}`).join(", ")}`}>
          {links.map((l) => (
            <path key={`${l.from}-${l.to}`} d={l.path} className="ribbon" style={{ ["--d" as string]: l.dot }}
              fill={l.to === TO ? "var(--heat-poor)" : heat(pppOf(l.to), league)} fillOpacity={0.3} />
          ))}
          {!reduce &&
            links.flatMap((l) => {
              const count = Math.min(14, Math.ceil(l.flow * 26));
              return Array.from({ length: count }, (_, i) => (
                <circle key={`${l.from}-${l.to}-${i}`} r={2.6} fill="var(--ink)" opacity={0}>
                  <animateMotion path={l.center} dur="1.5s" begin={`${0.35 + l.dot * 0.8 + (i / count) * 0.8}s`} repeatCount={3} fill="remove" />
                  <set attributeName="opacity" to={0.85} begin={`${0.35 + l.dot * 0.8 + (i / count) * 0.8}s`} dur="4.5s" />
                </circle>
              ));
            })}
          {nodes.map((n) => {
            const px = x(n.depth);
            const def = set.nodes[n.id];
            const shot = result.shots[n.id];
            const title = n.kind === "turnover" ? "Top kaybı" : (def?.label ?? n.id);
            const sub = shot
              ? `${nameOf(def?.shooter ?? "")}, ${shot.ppp_when_reached?.toFixed(2) ?? "-"} PPP`
              : null;
            return (
              <g key={n.id} className="ribbon" style={{ ["--d" as string]: n.depth }}>
                <rect x={px} y={n.y} width={BAR} height={n.h} fill={colorOf(n.id)} />
                <text x={px + BAR + 7} y={n.y + 4} dominantBaseline="hanging" fontSize={12.5} fontWeight={700} fill="var(--ink)" stroke="var(--bg)" strokeWidth={3.5} paintOrder="stroke" strokeLinejoin="round">
                  {title} <tspan fontWeight={500} fill="var(--muted)">%{(n.reach * 100).toFixed(0)}</tspan>
                </text>
                {sub && (
                  <text x={px + BAR + 7} y={n.y + 21} dominantBaseline="hanging" fontSize={11.5} fill="var(--muted)" stroke="var(--bg)" strokeWidth={3.5} paintOrder="stroke" strokeLinejoin="round">{sub}</text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </InView>
  );
}
