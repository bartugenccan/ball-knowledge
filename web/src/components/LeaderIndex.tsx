"use client";

import Link from "next/link";
import { useState } from "react";
import { InView } from "@/components/motion/InView";
import { Ticks } from "@/components/Ticks";
import { clubVars } from "@/lib/clubs";
import { tone } from "@/lib/format";

export type LeaderList = {
  key: string;
  label: string;
  players: { id: string; name: string; team: string; value: number }[];
};

/**
 * Leaders as one big index of attribute names. A row stretches when you point at it, and
 * opening it shows the top five.
 */
export function LeaderIndex({ lists }: { lists: LeaderList[] }) {
  const [open, setOpen] = useState<string | undefined>(lists[0]?.key);
  return (
    <div className="border-t-[3px] border-ink">
      {lists.map((l) => {
        const isOpen = open === l.key;
        const [lead, ...rest] = l.players;
        return (
          <div key={l.key} className="lead-row border-b border-ink" data-open={isOpen}>
            <button
              type="button"
              aria-expanded={isOpen}
              onClick={() => setOpen(isOpen ? undefined : l.key)}
              onPointerEnter={(e) => e.pointerType === "mouse" && setOpen(l.key)}
              className="grid w-full grid-cols-[1fr_auto] items-center gap-4 py-3 text-left md:py-4"
            >
              <span className="lead-name display text-[clamp(2.2rem,6vw,4.8rem)]" style={{ lineHeight: 1 }}>{l.label}</span>
              {lead && (
                <span className="flex items-center gap-3 md:gap-5">
                  <span lang="en" className="hidden text-right font-semibold sm:block">
                    {lead.name}
                    <span className="block text-xs font-normal text-muted">{lead.team}</span>
                  </span>
                  <span className={`club tile-${tone(lead.value)} num grid h-12 w-12 place-items-center text-2xl md:h-14 md:w-14 md:text-3xl`} style={clubVars(lead.team)}>{lead.value}</span>
                </span>
              )}
            </button>
            <div className="lead-body">
              <div>
                {isOpen && (
                  <InView amount={0} className="pb-5">
                    <p lang="en" className="mb-3 font-semibold sm:hidden">{lead?.name} <span className="text-xs font-normal text-muted">{lead?.team}</span></p>
                    <ol className="grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
                      {rest.map((p, i) => (
                        <li key={p.id} className="club" style={clubVars(p.team)}>
                          <Link href={`/players/${p.id}`} prefetch={false} className="group block">
                            <span className="mb-1 flex items-baseline justify-between gap-2 text-sm">
                              <span lang="en" className="truncate font-medium group-hover:text-accent-text">{p.name}</span>
                              <span className={`num text-lg ${tone(p.value)}`}>{p.value}</span>
                            </span>
                            <Ticks value={p.value} row={i * 3} />
                          </Link>
                        </li>
                      ))}
                    </ol>
                  </InView>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
