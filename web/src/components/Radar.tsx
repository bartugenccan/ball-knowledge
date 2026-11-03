"use client";

import { motion } from "motion/react";

/** Six-axis profile on the 1–20 scale. The shape grows out from the centre on first view. */
export function Radar({
  values,
  compare,
  size = 280,
}: {
  values: { label: string; value: number }[];
  compare?: { label: string; value: number }[];
  size?: number;
}) {
  const c = size / 2;
  const R = size / 2 - 42;
  const n = values.length;
  const pt = (i: number, v: number) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    const r = (Math.max(0, Math.min(20, v)) / 20) * R;
    return [c + r * Math.cos(a), c + r * Math.sin(a)] as const;
  };
  const poly = (vals: { value: number }[]) => vals.map((v, i) => pt(i, v.value).join(",")).join(" ");
  return (
    <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-[300px]" role="img"
      aria-label={values.map((v) => `${v.label} ${v.value.toFixed(0)}`).join(", ")}>
      {[5, 10, 15, 20].map((ring) => (
        <polygon key={ring} points={poly(values.map(() => ({ value: ring })))} fill="none"
          stroke="var(--line-2)" strokeWidth={ring === 20 ? 1.2 : 0.8} strokeDasharray={ring === 20 ? undefined : "2 4"} />
      ))}
      {values.map((_, i) => {
        const [x, y] = pt(i, 20);
        return <line key={i} x1={c} y1={c} x2={x} y2={y} stroke="var(--line)" />;
      })}
      {compare && (
        <polygon points={poly(compare)} fill="color-mix(in srgb, var(--muted) 14%, transparent)" stroke="var(--muted)"
          strokeWidth={1.2} strokeDasharray="4 3" />
      )}
      <motion.g
        style={{ transformOrigin: `${c}px ${c}px` }}
        initial={{ scale: 0.2, opacity: 0 }}
        whileInView={{ scale: 1, opacity: 1 }}
        viewport={{ once: true }}
        transition={{ type: "spring", stiffness: 120, damping: 16 }}
      >
        <polygon points={poly(values)} fill="color-mix(in srgb, var(--accent) 24%, transparent)" stroke="var(--accent)"
          strokeWidth={2} strokeLinejoin="round" />
        {values.map((v, i) => {
          const [x, y] = pt(i, v.value);
          return <circle key={i} cx={x} cy={y} r={3.5} fill="var(--accent)" />;
        })}
      </motion.g>
      {values.map((v, i) => {
        const [x, y] = pt(i, 26);
        return (
          <g key={v.label}>
            <text x={x} y={y - 4} textAnchor="middle" fontSize={11} fill="var(--muted)">{v.label}</text>
            <text x={x} y={y + 10} textAnchor="middle" fontSize={13} fontWeight={700} fill="var(--ink)"
              style={{ fontFamily: "var(--font-display)" }}>{v.value.toFixed(0)}</text>
          </g>
        );
      })}
    </svg>
  );
}
