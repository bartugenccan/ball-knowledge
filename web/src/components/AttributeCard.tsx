"use client";

import { motion } from "motion/react";
import { GROUP_LABEL, SOURCE_HINT, SOURCE_LABEL, tone } from "@/lib/format";
import type { AttributeMeta, Group, Rating } from "@/lib/types";

const GROUPS: Group[] = ["hucum", "savunma", "zihinsel"];
const EASE = [0.16, 1, 0.3, 1] as const;

/** Attribute grid: three groups, each row a label, an animated bar and a 1–20 chip. */
export function AttributeCard({
  attributes,
  ratings,
  compare,
  windowKey = "season",
}: {
  attributes: AttributeMeta[];
  ratings: Rating[];
  compare?: Rating[];
  windowKey?: string;
}) {
  const byKey = new Map(ratings.map((r) => [r.key, r]));
  const cmp = compare ? new Map(compare.map((r) => [r.key, r])) : null;
  let row = 0;
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {GROUPS.map((g) => (
        <section key={g} className="panel p-4">
          <h3 className="mb-3 font-display text-lg font-semibold uppercase tracking-wide text-muted">{GROUP_LABEL[g]}</h3>
          <ul className="space-y-2.5">
            {attributes
              .filter((a) => a.group === g)
              .map((a) => {
                const r = byKey.get(a.key);
                if (!r) return null;
                const i = row++;
                const delta = cmp ? r.value - (cmp.get(a.key)?.value ?? r.value) : 0;
                const t = tone(r.value);
                return (
                  <li key={a.key} className="group">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="flex-1 truncate" title={`${a.description}\n${SOURCE_HINT[a.source]}`}>
                        {a.label}
                        {a.source === "tahmini" && (
                          <span className="ml-1.5 rounded-full bg-[var(--accent-soft)] px-1.5 py-px text-[10px] text-accent">
                            {SOURCE_LABEL[a.source]}
                          </span>
                        )}
                        {a.source === "turetilmis" && <span className="ml-1.5 text-[10px] text-dim">türetilmiş</span>}
                      </span>
                      {cmp && delta !== 0 && (
                        <span className={`font-mono text-xs ${delta > 0 ? "r-elite" : "r-poor"}`}>{delta > 0 ? `+${delta}` : delta}</span>
                      )}
                      <span className={`chip-${t} grid h-7 w-9 place-items-center rounded-lg font-display text-lg font-bold`}>
                        {r.value}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <div className="relative h-1 flex-1 overflow-hidden rounded-full bg-line/60">
                        <motion.div
                          key={`${windowKey}-${a.key}`}
                          className={`fill-${t} absolute inset-y-0 left-0 w-full origin-left rounded-full`}
                          initial={{ scaleX: 0 }}
                          whileInView={{ scaleX: r.value / 20 }}
                          viewport={{ once: true }}
                          transition={{ duration: 0.8, delay: i * 0.03, ease: EASE }}
                        />
                      </div>
                      <Confidence conf={r.conf} />
                    </div>
                  </li>
                );
              })}
          </ul>
        </section>
      ))}
    </div>
  );
}

function Confidence({ conf }: { conf: number }) {
  const n = conf >= 0.66 ? 3 : conf >= 0.33 ? 2 : 1;
  const label = n === 3 ? "yüksek" : n === 2 ? "orta" : "düşük";
  return (
    <span className="flex gap-0.5" title={`Güven: ${label} (${Math.round(conf * 100)}%)`} aria-label={`güven ${label}`}>
      {[1, 2, 3].map((k) => (
        <span key={k} className={`h-1 w-2 rounded-full ${k <= n ? "bg-muted" : "bg-line-2"}`} />
      ))}
    </span>
  );
}
