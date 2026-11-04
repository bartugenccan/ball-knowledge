import { AttributeHintCard } from "@/components/AttributeHintCard";
import { InView } from "@/components/motion/InView";
import { Ticks } from "@/components/Ticks";
import { GROUP_LABEL, labelTone, SOURCE_LABEL, tone } from "@/lib/format";
import type { AttributeMeta, Group, Rating } from "@/lib/types";

const GROUPS: Group[] = ["hucum", "savunma", "zihinsel"];

/** Three columns of attributes. Each row: label, number and a 20-lamp rail. */
export function AttributeCard({ attributes, ratings, compare }: { attributes: AttributeMeta[]; ratings: Rating[]; compare?: Rating[] }) {
  const byKey = new Map(ratings.map((r) => [r.key, r]));
  const cmp = compare ? new Map(compare.map((r) => [r.key, r])) : null;
  let row = 0;
  return (
    <InView className="grid gap-x-10 gap-y-8 lg:grid-cols-3" amount={0.1}>
      {GROUPS.map((g) => (
        <section key={g}>
          <h3 className="display t-sub mb-4 border-b-2 border-ink pb-2">{GROUP_LABEL[g]}</h3>
          <ul className="space-y-3">
            {attributes
              .filter((a) => a.group === g)
              .map((a) => {
                const r = byKey.get(a.key);
                if (!r) return null;
                const i = row++;
                const shown = r.display ?? String(r.value);
                const isNumber = shown === String(r.value);
                const delta = cmp && isNumber ? r.value - (cmp.get(a.key)?.value ?? r.value) : 0;
                const hasRange = isNumber && r.lo !== undefined && r.hi !== undefined;
                return (
                  <li key={a.key} className="hint">
                    <div className="mb-1 flex items-baseline gap-2 text-sm">
                      <button type="button" className="hint-trigger flex-1 truncate text-left font-medium" aria-describedby={`hint-${a.key}`}>
                        {a.label}
                        {a.source === "tahmini" && <span className="ml-1.5 text-[11px] font-semibold text-accent-text">{SOURCE_LABEL[a.source]}</span>}
                        {a.source === "turetilmis" && <span className="ml-1.5 text-[11px] text-dim">türetilmiş</span>}
                      </button>
                      {r.low_data && isNumber && (
                        <span className="text-[11px] font-medium text-dim" title="Oyuncunun kendi verisi tahminin dörtte birinden az. Puan çoğunlukla beklentiden geliyor; liderlik listelerine girmez.">az veri</span>
                      )}
                      {hasRange && (
                        <span className="num text-xs text-dim" title="Puanın büyük olasılıkla (%80) bulunduğu aralık">{r.lo}–{r.hi}</span>
                      )}
                      {cmp && delta !== 0 && (
                        <span className={`text-xs font-semibold ${delta > 0 ? "r-elite" : "r-poor"}`}>{delta > 0 ? `+${delta}` : delta}</span>
                      )}
                      {isNumber ? (
                        <span className={`num w-7 text-right text-xl ${tone(r.value)}`}>{r.value}</span>
                      ) : (
                        <span className={`whitespace-nowrap text-right text-sm font-semibold ${labelTone(shown)}`}>{shown}</span>
                      )}
                    </div>
                    {isNumber && <Ticks value={r.value} row={i} />}
                    <AttributeHintCard attribute={a} />
                  </li>
                );
              })}
          </ul>
        </section>
      ))}
    </InView>
  );
}
