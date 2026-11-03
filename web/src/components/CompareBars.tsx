"use client";

import { motion } from "motion/react";
import { GROUP_LABEL, tone } from "@/lib/format";
import type { AttributeMeta, Group, Rating } from "@/lib/types";

/** Mirrored bars growing outward from the centre line; the winner of each row is lit in the accent. */
export function CompareBars({ attributes, a, b }: { attributes: AttributeMeta[]; a: Rating[]; b: Rating[] }) {
  const va = new Map(a.map((r) => [r.key, r.value]));
  const vb = new Map(b.map((r) => [r.key, r.value]));
  let i = 0;
  return (
    <div className="space-y-6">
      {(Object.keys(GROUP_LABEL) as Group[]).map((g) => (
        <section key={g} className="panel p-4 md:p-5">
          <h3 className="mb-3 text-center font-display text-lg font-semibold uppercase tracking-wide text-muted">{GROUP_LABEL[g]}</h3>
          <ul className="space-y-2">
            {attributes.filter((x) => x.group === g).map((attr) => {
              const x = va.get(attr.key) ?? 0;
              const y = vb.get(attr.key) ?? 0;
              const d = i++ * 0.025;
              return (
                <li key={attr.key} className="grid grid-cols-[2.5rem_1fr_minmax(6rem,9rem)_1fr_2.5rem] items-center gap-2 text-sm">
                  <span className={`text-right font-display text-xl font-bold ${tone(x)}`}>{x}</span>
                  <Bar value={x} win={x > y} side="left" delay={d} />
                  <span className="truncate text-center text-xs text-muted">{attr.label}</span>
                  <Bar value={y} win={y > x} side="right" delay={d} />
                  <span className={`font-display text-xl font-bold ${tone(y)}`}>{y}</span>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Bar({ value, win, side, delay }: { value: number; win: boolean; side: "left" | "right"; delay: number }) {
  return (
    <div className="h-2 overflow-hidden rounded-full bg-line/50">
      <motion.div
        className={`h-full w-full rounded-full ${side === "left" ? "origin-right" : "origin-left"}`}
        style={{ background: win ? "var(--accent)" : "var(--muted)", opacity: win ? 1 : 0.4 }}
        initial={{ scaleX: 0 }}
        whileInView={{ scaleX: value / 20 }}
        viewport={{ once: true }}
        transition={{ duration: 0.8, delay, ease: [0.16, 1, 0.3, 1] }}
      />
    </div>
  );
}
