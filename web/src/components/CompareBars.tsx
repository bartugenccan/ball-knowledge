import { InView } from "@/components/motion/InView";
import { Ticks } from "@/components/Ticks";
import { GROUP_LABEL, labelTone } from "@/lib/format";
import type { AttributeMeta, Group, Rating } from "@/lib/types";

/** Mirrored lamp rails growing outward from a shared spine; the side that loses the row dims. */
export function CompareBars({ attributes, a, b }: { attributes: AttributeMeta[]; a: Rating[]; b: Rating[] }) {
  const va = new Map(a.map((r) => [r.key, r.value]));
  const vb = new Map(b.map((r) => [r.key, r.value]));
  const textOf = (list: Rating[], key: string) => list.find((r) => r.key === key)?.display;
  let i = 0;
  return (
    <InView className="grid gap-x-12 gap-y-10 xl:grid-cols-2" amount={0.05}>
      {(Object.keys(GROUP_LABEL) as Group[]).map((g) => (
        <section key={g} className={g === "hucum" ? "xl:row-span-2" : ""}>
          <h3 className="display t-sub mb-4 border-b-2 border-ink pb-2">{GROUP_LABEL[g]}</h3>
          <ul className="space-y-3">
            {attributes.filter((x) => x.group === g).map((attr) => {
              const x = va.get(attr.key) ?? 0;
              const y = vb.get(attr.key) ?? 0;
              const row = i++;
              const tx = textOf(a, attr.key) ?? String(x);
              const ty = textOf(b, attr.key) ?? String(y);
              if (tx !== String(x) || ty !== String(y)) {
                // tiers and statements have no fine-grained number to compare
                return (
                  <li key={attr.key} className="flex items-baseline justify-between gap-3">
                    <span className={`text-sm font-semibold ${labelTone(tx)}`}>{tx}</span>
                    <span className="truncate text-center text-xs font-medium text-muted">{attr.label}</span>
                    <span className={`text-right text-sm font-semibold ${labelTone(ty)}`}>{ty}</span>
                  </li>
                );
              }
              return (
                <li key={attr.key}>
                  <div className="mb-1 flex items-baseline justify-between gap-3">
                    <span className="num w-8 text-2xl" style={{ color: x >= y ? "var(--side-a-t)" : "var(--dim)" }}>{x}</span>
                    <span className="truncate text-center text-xs font-medium text-muted">{attr.label}</span>
                    <span className="num w-8 text-right text-2xl" style={{ color: y >= x ? "var(--side-b-t)" : "var(--dim)" }}>{y}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-1">
                    <Ticks value={x} row={row} color="var(--side-a)" rtl dim={x < y} />
                    <Ticks value={y} row={row} color="var(--side-b)" dim={y < x} />
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </InView>
  );
}
