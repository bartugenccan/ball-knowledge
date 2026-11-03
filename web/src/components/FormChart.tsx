"use client";

import { motion } from "motion/react";
import type { GameLine } from "@/lib/types";

/** Match-rating timeline (1–10). The line draws itself left to right; 6.6 is an ordinary outing. */
export function FormChart({ games }: { games: GameLine[] }) {
  if (games.length === 0) return <p className="text-sm text-muted">Bu sezon maç yok.</p>;
  const W = 640;
  const H = 200;
  const pad = { l: 28, r: 10, t: 14, b: 22 };
  const lo = 3;
  const hi = 10;
  const x = (i: number) => pad.l + (games.length === 1 ? 0.5 : i / (games.length - 1)) * (W - pad.l - pad.r);
  const y = (v: number) => pad.t + ((hi - v) / (hi - lo)) * (H - pad.t - pad.b);
  const line = games.map((g, i) => `${i ? "L" : "M"}${x(i)},${y(g.game_rating)}`).join(" ");
  const area = `${line} L${x(games.length - 1)},${H - pad.b} L${x(0)},${H - pad.b} Z`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Maç puanı grafiği">
      <defs>
        <linearGradient id="form-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.35} />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
        </linearGradient>
      </defs>
      {[4, 6, 8, 10].map((v) => (
        <g key={v}>
          <line x1={pad.l} x2={W - pad.r} y1={y(v)} y2={y(v)} stroke="var(--line)" />
          <text x={pad.l - 8} y={y(v) + 4} textAnchor="end" fontSize={11} fill="var(--dim)">{v}</text>
        </g>
      ))}
      <line x1={pad.l} x2={W - pad.r} y1={y(6.6)} y2={y(6.6)} stroke="var(--muted)" strokeDasharray="3 5" />
      <motion.path d={area} fill="url(#form-fill)"
        initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }}
        transition={{ duration: 0.8, delay: 0.5 }} />
      <motion.path d={line} fill="none" stroke="var(--accent)" strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round"
        initial={{ pathLength: 0 }} whileInView={{ pathLength: 1 }} viewport={{ once: true }}
        transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }} />
      {games.map((g, i) => (
        <motion.circle key={g.gamecode} cx={x(i)} cy={y(g.game_rating)} r={4.5} fill="var(--bg)" stroke="var(--accent)" strokeWidth={2}
          initial={{ scale: 0 }} whileInView={{ scale: 1 }} viewport={{ once: true }}
          transition={{ delay: 0.15 + (i / games.length) * 0.9, type: "spring", stiffness: 300, damping: 18 }}
          style={{ transformBox: "fill-box", transformOrigin: "center" }}
          whileHover={{ scale: 1.6 }}>
          <title>{`Tur ${g.round ?? "?"}, ${g.is_home ? "vs" : "@"} ${g.opponent}: ${g.game_rating} (${g.pts} sayı, ${g.minutes.toFixed(0)} dk)`}</title>
        </motion.circle>
      ))}
    </svg>
  );
}
