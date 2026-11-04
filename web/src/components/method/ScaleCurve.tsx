import { InView } from "@/components/motion/InView";
import { tone } from "@/lib/format";

const SCALE = Array.from({ length: 20 }, (_, i) => i + 1);
const MAX_STACK = 13;

/** Theoretical shape of the 1-20 scale (11.5 + 3.2z), built out of cards. */
export function ScaleCurve() {
  return (
    <InView amount={0.3} className="not-prose">
      <div className="grid items-end gap-1" style={{ gridTemplateColumns: "repeat(20, minmax(0, 1fr))" }} role="img" aria-label="1-20 ölçeğinin dağılımı: ortalama 11,5 civarında yoğunlaşan çan eğrisi">
        {SCALE.map((v, c) => {
          const z = (v - 11.5) / 3.2;
          const stack = Math.max(1, Math.round(MAX_STACK * Math.exp((-z * z) / 2)));
          return (
            <div key={v} className="grid gap-px">
              {Array.from({ length: stack }, (_, i) => (
                <span key={i} className={`curve-tile in tile-${tone(v)}`} style={{ ["--d" as string]: c * 3 + (stack - i) }} />
              ))}
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 grid gap-1 border-t-2 border-ink pt-1" style={{ gridTemplateColumns: "repeat(20, minmax(0, 1fr))" }}>
        {SCALE.map((v) => <span key={v} className={`num text-center text-[10px] sm:text-sm ${tone(v)}`}>{v}</span>)}
      </div>
    </InView>
  );
}
