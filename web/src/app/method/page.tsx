import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/Skeleton";
import { getMeta } from "@/lib/api";
import { GROUP_LABEL, SOURCE_HINT, SOURCE_LABEL } from "@/lib/format";
import type { Group, Source } from "@/lib/types";

export const metadata: Metadata = { title: "Yöntem" };

export default function MethodPage() {
  return (
    <article className="max-w-3xl space-y-8 text-[15px] leading-relaxed text-muted [&_strong]:text-ink [&_h2]:text-ink [&_h1]:text-ink [&_code]:rounded-md [&_code]:bg-panel-2 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-accent">
      <h1 className="font-display text-5xl font-extrabold uppercase tracking-tight">Puanlar nasıl hesaplanıyor?</h1>

      <section className="space-y-2">
        <h2 className="font-display text-2xl font-bold uppercase tracking-wide">1. Veri</h2>
        <p>
          Her maçın play-by-play akışı, şut koordinatları ve kutu skoru EuroLeague’in açık istatistik uçlarından çekilir.
          Play-by-play’deki oyuncu değişikliklerinden her an sahada olan beşliler, her oyuncunun kesintisiz süresi (stint)
          ve her possession’ın kimde olduğu yeniden kurulur. Kontrol: possession’lardan toplanan sayı her maçta resmi
          skorla aynıdır.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="font-display text-2xl font-bold uppercase tracking-wide">2. Küçük örneklem düzeltmesi</h2>
        <p>
          Her oran lig ortalamasına doğru çekilir: <code>(isabet + k·lig_oranı) / (deneme + k)</code>. Örneğin üçlükte
          k = 400: 3’te 3 atan bir oyuncu %36,5’e, 1000’de 450 atan bir oyuncu %42’ye iner. Güven noktaları, verinin bu
          çekişe ne kadar karşı koyduğunu gösterir.
        </p>
        <p>
          k değerleri tahmin gücüne göre seçildi: önceki ayların verisiyle sonraki ayın şutları tahmin edildi. Pota altı
          becerisi çabuk ortaya çıkıyor (k = 50). Orta mesafe ve üçlük yüzdeleri ise ancak yüzlerce denemeden sonra lig
          ortalamasından daha iyi bir tahminci oluyor (k = 400).
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="font-display text-2xl font-bold uppercase tracking-wide">3. 1–20 ölçeği</h2>
        <p>
          Düzeltilmiş değer, o sezon yeterli süre alan oyuncular içindeki yüzdelik dilime göre normal dağılım skoruna
          çevrilir ve <code>11,5 + 3,2·z</code> olarak 1–20’ye yerleştirilir. EuroLeague elit bir lig olduğu için ortalama
          rotasyon oyuncusu 11–12 civarındadır. Ligin en iyisi 20’ye yaklaşır, en zayıfı 3 civarında kalır. Aylık puanlar
          sezonla aynı ölçekte hesaplanır.
        </p>
        <p>
          <strong>Maç puanı</strong> (1–10) ayrı bir göstergedir: Hollinger game score’un oynanan süreye göre beklenen
          değerden sapması. 6,6 sıradan bir maçtır.
        </p>
      </section>

      <Suspense fallback={<Skeleton className="h-64" />}>
        <AttributeTable />
      </Suspense>

      <section className="space-y-2">
        <h2 className="font-display text-2xl font-bold uppercase tracking-wide">4. Açık veride olmayanlar</h2>
        <p>
          Şutu kimin savunduğu, contest mesafesi ve set tipleri (pick and roll vb.) açık veride yoktur. Bu yüzden
          <em> Çevre Savunması</em> ve <em>Pota Koruma</em>, oyuncu sahadayken rakibin şut isabetinin beklentiye göre
          sapmasından dolaylı olarak tahmin edilir ve “Tahmini” etiketi taşır. Set simülatöründeki boş ve contest edilmiş
          şut farkı da yayımlanmış NBA takip verisinden alınan bir önsel değerdir. Koç bu değeri değiştirebilir.
        </p>
      </section>
    </article>
  );
}

async function AttributeTable() {
  const meta = await getMeta();
  return (
    <section className="space-y-2">
      <h2 className="font-display text-2xl font-bold uppercase tracking-wide">Özellikler ve kaynakları</h2>
      <ul className="space-y-1 text-sm text-muted">
        {(Object.keys(SOURCE_LABEL) as Source[]).map((s) => (
          <li key={s}>
            <strong className="text-ink">{SOURCE_LABEL[s]}:</strong> {SOURCE_HINT[s]}
          </li>
        ))}
      </ul>
      <div className="panel divide-y divide-line">
        {(Object.keys(GROUP_LABEL) as Group[]).map((g) => (
          <div key={g} className="p-3">
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted">{GROUP_LABEL[g]}</h3>
            <dl className="grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
              {meta.attributes
                .filter((a) => a.group === g)
                .map((a) => (
                  <div key={a.key} className="contents">
                    <dt className="font-medium">
                      {a.label} <span className="text-xs text-muted">({SOURCE_LABEL[a.source]})</span>
                    </dt>
                    <dd className="text-muted">{a.description}</dd>
                  </div>
                ))}
            </dl>
          </div>
        ))}
      </div>
    </section>
  );
}
