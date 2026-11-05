import Link from "next/link";
import type { RotationRow, StyleMetric, TeamStyle as Style } from "@/lib/match";
import type { AttributeMeta } from "@/lib/types";

const MINUTES = 40;
const QUARTERS = ["1. çeyrek", "2. çeyrek", "3. çeyrek", "4. çeyrek"];

function value(m: { value: number; unit: string; digits: number }) {
  return `${m.value.toFixed(m.digits)}${m.unit}`;
}

/** Where a team sits between the league's lowest and highest team, with the league average marked. */
function RangeStrip({ m }: { m: StyleMetric }) {
  const span = m.high - m.low || 1;
  const at = (x: number) => `${Math.min(100, Math.max(0, (100 * (x - m.low)) / span))}%`;
  return (
    <div className="relative h-4" role="img" aria-label={`${m.label}: ${value(m)}, lig ortalaması ${m.league.toFixed(m.digits)}${m.unit}, ${m.teams} takım içinde ${m.rank}. sıra`}>
      <div className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 bg-line" />
      <div className="absolute top-0 h-4 w-0.5 -translate-x-1/2 bg-dim" style={{ left: at(m.league) }} title={`Lig: ${m.league.toFixed(m.digits)}${m.unit}`} />
      <div
        className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-bg"
        style={{ left: at(m.value), background: m.stable ? "var(--accent)" : "var(--muted)" }}
        title={`${value(m)} (${m.rank}/${m.teams})`}
      />
    </div>
  );
}

function MetricRow({ m, labels }: { m: StyleMetric; labels: Map<string, string> }) {
  return (
    <li className="space-y-1">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-semibold" title={m.hint}>
          {m.label}
          {!m.stable && (
            <span className="ml-2 text-xs font-normal text-dim" title={`İlk 10 maç, kalan maçları zayıf öngörüyor (${m.stability?.toFixed(2)}). Hafta hafta değişebilir.`}>
              dalgalı
            </span>
          )}
        </span>
        <span className="whitespace-nowrap text-sm">
          <span className="num">{value(m)}</span>
          <span className="ml-2 text-xs text-muted">{m.rank}/{m.teams}</span>
        </span>
      </div>
      <RangeStrip m={m} />
      {m.carriers.length > 0 && (
        <p className="text-xs text-muted">
          {labels.get(m.carriers[0].attribute)}:{" "}
          {m.carriers.map((c, i) => (
            <span key={c.name}>
              {i > 0 && ", "}
              <span lang="en">{c.name}</span> {c.shown}
            </span>
          ))}
        </p>
      )}
    </li>
  );
}

/** Who plays when: one row per player, one cell per game minute, darker means more often on court. */
function RotationHeat({ rows, season }: { rows: RotationRow[]; season: string }) {
  return (
    <div className="overflow-x-auto">
      {/* fixed layout: otherwise empty cells collapse and the first cell of each quarter takes all the width */}
      <table className="w-full min-w-[640px] table-fixed border-separate border-spacing-0 text-xs">
        <colgroup>
          <col className="w-32" />
          <col className="w-12" />
          {Array.from({ length: MINUTES }, (_, m) => <col key={m} />)}
        </colgroup>
        <thead>
          <tr>
            <th scope="col" className="w-32 pb-1 text-left font-semibold text-muted">Oyuncu</th>
            <th scope="col" className="w-12 pb-1 text-right font-semibold text-muted">Dk/M</th>
            {QUARTERS.map((q) => (
              <th key={q} scope="colgroup" colSpan={10} className="pb-1 pl-1 text-left font-semibold text-muted">{q}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.player_id}>
              <th scope="row" className="truncate whitespace-nowrap py-px pr-2 text-left font-semibold">
                <Link lang="en" prefetch={false} href={`/players/${r.player_id}?season=${season}`} className="hover:text-accent-text">{r.name}</Link>
              </th>
              <td className="num pr-2 text-right text-muted">{r.mpg.toFixed(1)}</td>
              {r.curve.slice(0, MINUTES).map((q, m) => (
                <td
                  key={m}
                  className={`h-5 p-0 ${m % 10 === 0 ? "border-l-2 border-bg" : ""}`}
                  style={{ background: `color-mix(in oklab, var(--accent) ${Math.round(q * 100)}%, var(--bg-2))` }}
                  title={`${r.name}, ${m + 1}. dakika: sahada olma sıklığı %${Math.round(q * 100)}`}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 flex items-center gap-2 text-xs text-muted">
        <span>Nadiren sahada</span>
        <span className="h-2 w-24 rounded-sm" style={{ background: "linear-gradient(to right, var(--bg-2), var(--accent))" }} />
        <span>Neredeyse hep sahada</span>
      </div>
    </div>
  );
}

export function TeamStyle({ style, attributes }: { style: Style; attributes: AttributeMeta[] }) {
  const labels = new Map(attributes.map((a) => [a.key, a.label]));
  const groups = Object.entries(style.groups);
  const { efficiency: e } = style;
  return (
    <section className="space-y-8 pt-6" aria-labelledby="style-title">
      <header className="space-y-3 border-t-2 border-ink pt-5">
        <h2 id="style-title" className="display t-sec">Nasıl oynuyor?</h2>
        {style.early && (
          <p className="max-w-[70ch] text-sm text-muted">
            Sezonun başı: {style.games} maçlık veri. Eğilimler henüz oturmamış olabilir; hangi ölçümün ne kadar güvenilir olduğu aşağıda işaretli.
          </p>
        )}
        {style.summary.length > 0 ? (
          <ul className="max-w-[80ch] space-y-1.5">
            {style.summary.map((s) => <li key={s}>{s}</li>)}
          </ul>
        ) : (
          <p className="max-w-[70ch] text-muted">Güvenilir ölçümlerin hiçbirinde ligin uçlarında değil: belirgin bir aşırılığı olmayan, dengeli bir profil.</p>
        )}
        <p className="text-sm text-muted">
          100 hücumda <span className="num text-ink">{e.off.toFixed(1)}</span> sayı atıyor, <span className="num text-ink">{e.def.toFixed(1)}</span> yiyor.
          Net fark ligde {e.net_rank}/{e.teams}.
          {style.similar.length > 0 && (
            <>
              {" "}Oyun profili en çok benzeyenler:{" "}
              {style.similar.map((t, i) => (
                <span key={t.code}>
                  {i > 0 && ", "}
                  <Link lang="en" prefetch={false} href={`/teams/${t.code}?season=${style.season}`} className="underline underline-offset-2 hover:text-accent-text">{t.name}</Link>
                </span>
              ))}.
            </>
          )}
        </p>
      </header>

      <div className="grid gap-x-12 gap-y-8 md:grid-cols-2 xl:grid-cols-3">
        {groups.filter(([k]) => k !== "rotation").map(([key, label]) => (
          <div key={key}>
            <h3 className="display t-sub mb-3 border-b-2 border-ink pb-1.5">{label}</h3>
            <ul className="space-y-4">
              {style.metrics.filter((m) => m.group === key).map((m) => <MetricRow key={m.key} m={m} labels={labels} />)}
            </ul>
          </div>
        ))}
        {style.assist_pairs.length > 0 && (
          <div>
            <h3 className="display t-sub mb-3 border-b-2 border-ink pb-1.5">En çok işleyen paslar</h3>
            <ul className="space-y-1.5 text-sm">
              {style.assist_pairs.map((p) => (
                <li key={`${p.from}-${p.to}`} className="flex justify-between gap-3">
                  <span lang="en" className="font-semibold">{p.from} → {p.to}</span>
                  <span className="whitespace-nowrap text-muted"><span className="num text-ink">{p.count}</span> asist, {p.points} sayı</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div>
        <h3 className="display t-sub mb-1">Rotasyon: kim ne zaman sahada?</h3>
        <p className="mb-3 max-w-[70ch] text-sm text-muted">
          Her hücre, oyuncunun oynadığı maçlarda o dakikada sahada olma sıklığı. Koçun ritmi buradan okunur: beşlinin ne zaman dinlendiği, kimin maçı bitirdiği.
        </p>
        <RotationHeat rows={style.rotation} season={style.season} />
        <ul className="mt-5 grid gap-x-12 gap-y-4 md:grid-cols-2">
          {style.metrics.filter((m) => m.group === "rotation").map((m) => <MetricRow key={m.key} m={m} labels={labels} />)}
        </ul>
      </div>

      <p className="max-w-[75ch] text-xs text-dim">
        Noktalar takımın yerini, çizgi ligin en düşük ve en yüksek takımını, dikey işaret lig ortalamasını gösterir. Veride oyun tipi, perdeler ya da savunmacı eşleşmesi
        yok; bu yüzden burada takımın ne yaptığı var, setleri nasıl kurduğu yok. &quot;Dalgalı&quot; işaretli ölçümlerde ilk 10 maç sezonun geri kalanını iyi öngörmüyor.
      </p>
    </section>
  );
}
