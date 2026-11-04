import type { Metadata } from "next";
import { Suspense } from "react";
import { ScaleCurve } from "@/components/method/ScaleCurve";
import { ShrinkDemo } from "@/components/method/ShrinkDemo";
import { Skeleton } from "@/components/Skeleton";
import { getMeta } from "@/lib/api";
import { GROUP_LABEL, SOURCE_HINT, SOURCE_LABEL } from "@/lib/format";
import type { Group, Source } from "@/lib/types";

export const metadata: Metadata = { title: "Yöntem" };

const H2 = "display t-sec text-ink";
const TOC = [
  ["veri", "Veri"],
  ["orneklem", "Küçük örneklem"],
  ["olcek", "1-20 ölçeği"],
  ["ozellikler", "Özellikler"],
  ["eksikler", "Ölçülemeyenler"],
];

export default function MethodPage() {
  return (
    <div className="wrap pt-8">
      <h1 className="display t-page stretch-in max-w-[14ch]">Puanlar nasıl hesaplanıyor?</h1>
      <div className="mt-14 grid gap-x-16 lg:grid-cols-[minmax(0,46rem)_minmax(0,1fr)]">
      <article className="min-w-0 space-y-14 text-[1.0625rem] leading-relaxed text-muted [&_code]:bg-bg-2 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[0.9em] [&_code]:text-ink [&_strong]:text-ink">
        <section id="veri" className="scroll-target space-y-4">
          <h2 className={H2}>Veri</h2>
          <p>
            Her maçın play-by-play akışı, şut koordinatları ve kutu skoru EuroLeague&apos;in açık istatistik uçlarından çekilir. Boy ve
            pozisyon resmi kadro kayıtlarından gelir. Play-by-play&apos;deki oyuncu değişikliklerinden her an sahada olan beşliler, her
            oyuncunun kesintisiz süresi (stint) ve her possession&apos;ın kimde olduğu yeniden kurulur.
          </p>
          <p>
            Sezon toplamları resmi toplamlarla karşılaştırılır. Son karşılaştırmada yaklaşık 15.600 değerin 17&apos;si farklıydı, en büyük
            fark 2. Possession&apos;lardan toplanan sayı her maçta resmi skorla aynıdır. Periyot sonu umut atışları yüzdelerden çıkarılır.
            Koordinatı hatalı şutlar bölge hesabına girmez.
          </p>
        </section>

        <section id="orneklem" className="scroll-target space-y-4">
          <h2 className={H2}>Küçük örneklem düzeltmesi</h2>
          <p>
            Her oran bir beklentiye doğru çekilir: <code>(isabet + k·beklenti) / (deneme + k)</code>. Beklenti, testte tahmini
            iyileştirdiği özelliklerde oyuncunun boyu, pozisyonu ve ilgili yan verileridir (üçlükte serbest atışı). Diğerlerinde lig
            ortalamasıdır. Önceki sezonlar da testte işe yaradığı ölçüde hesaba katılır.
          </p>
          <ShrinkDemo />
          <p>
            k değerleri elle seçilmez: sezonun ilk yarısından ikinci yarısı, bir sezondan sonraki sezon tahmin edilerek belirlenir ve
            son sezon bu seçimin dışında bırakılarak kontrol edilir. Blok gibi beceriler çabuk ortaya çıkar (k = 40). Üçlük yüzdesi çok
            daha yavaş yerleşir (k = 400).
          </p>
          <p>
            Yüzde tek başına yetmez. Üçlük, Orta Mesafe ve Bitiricilik isabetle birlikte kullanım hacmini de sayar; Bitiricilik ayrıca
            oyuncunun kendi yarattığı isabetlere bakar. Az şutla yüksek yüzde bu yüzden tepeye çıkmaz. Top Güvenliği de az top kaybını top
            kullanımıyla birlikte değerlendirir: topa az dokunan oyuncu az kaybettiği için ödüllendirilmez.
          </p>
        </section>

        <section id="olcek" className="scroll-target space-y-4">
          <h2 className={H2}>1-20 ölçeği</h2>
          <p>
            Düzeltilmiş değer, en az 500 dakika oynanan tam sezonlardan oluşan sabit bir referansla karşılaştırılır. Yüzdelik dilim normal
            dağılım skoruna çevrilir ve <code>11,5 + 3,2·z</code> olarak 1-20&apos;ye yerleştirilir. Karşılaştırma ligin o dönemki seviyesine
            göre yapılır. Referans sabit olduğu için sezon başında az verisi olan oyuncu ortaya yakın kalır; uç puan için gerçek kanıt gerekir.
          </p>
          <ScaleCurve />
          <p>
            Puanın yanındaki aralık, puanın büyük olasılıkla (%80) bulunduğu yeri gösterir. Oyuncunun kendi verisi tahminin dörtte birinden
            azsa <strong>az veri</strong> yazar ve oyuncu liderlik listelerine girmez. Maçta 10 dakikadan az oynayanlar da bu listelerde yer almaz, ama puanları kartlarında görünür.
          </p>
          <p>
            Aylık puan formu gösterir: o ayın verisi, oyuncunun o aydan önceki seviyesine doğru çekilir. <strong>Maç puanı</strong> (1-10) ayrı bir
            göstergedir: Hollinger game score&apos;un oynanan süreye göre beklenen değerden sapması. 6,6 sıradan bir maçtır. O maçı özetler,
            sonraki maçı tahmin etmez.
          </p>
        </section>

        <Suspense fallback={<Skeleton className="h-64" />}>
          <AttributeTable />
        </Suspense>

        <section id="eksikler" className="scroll-target space-y-4">
          <h2 className={H2}>Veride olmayanlar ve ölçülemeyenler</h2>
          <p>
            Şutu kimin savunduğu, contest mesafesi ve set tipleri açık veride yoktur. <em>Pota Koruma</em> ve <em>Savunma Etkisi</em>, oyuncu
            sahadayken rakibin ürettiğinin takım arkadaşlarından ayrılarak tahmin edilmesiyle bulunur ve &quot;Tahmini&quot; etiketi taşır. Pota
            Koruma&apos;nın yarısı blok payıdır: saha içi etki tek başına kısa sürede güvenilir değildir.
          </p>
          <p>Bazı özellikler bu veriyle beklediğimiz hassasiyette ölçülemiyor. Bunları sayıymış gibi göstermiyoruz:</p>
          <ul className="list-disc space-y-2 pl-5">
            <li><strong>Clutch:</strong> Sezonlar arasında kalıcı bir oyuncu farkı görülmüyor. Oyuncu kartında bu sezonun clutch sayıları yazar, puan verilmez.</li>
            <li><strong>Köşe üçlük:</strong> Köşe isabeti gerçekten daha yüksek, ama genel üçlükten ayrı bir beceri görülmüyor. Kartta bilgi olarak yer alır.</li>
            <li><strong>Çevre Savunması ve Orta Mesafe:</strong> Düşük, Orta ve Yüksek olarak gösterilir, çünkü 1-20 var olmayan bir hassasiyet ima eder.</li>
            <li><strong>Pota altı ile boyalı alan:</strong> Yakın şutlar salondan salona farklı işaretlendiği için birlikte değerlendirilir.</li>
            <li><strong>Oyun Yükü:</strong> Dakika ve uzun seri payını gösterir. Fiziksel dayanıklılık ölçümü değildir, antrenörün rotasyonunu da yansıtır.</li>
            <li><strong>İstikrar:</strong> 20 maçtan önce değerlendirilmez.</li>
          </ul>
          <p>
            Set simülatöründeki boş ve contest edilmiş şut farkı yayımlanmış NBA takip verisinden alınan bir önsel değerdir. Koç bu değeri
            değiştirebilir. Yorgunluk ve clutch etkisi simülatörde oyuncuya göre değil, lig geneli olarak uygulanır.
          </p>
        </section>
      </article>
      <nav aria-label="Bu sayfada" className="sticky top-24 hidden self-start lg:block">
        <ul className="space-y-1">
          {TOC.map(([id, label]) => (
            <li key={id}><a href={`#${id}`} className="nav-link">{label}</a></li>
          ))}
        </ul>
      </nav>
      </div>
    </div>
  );
}

async function AttributeTable() {
  const meta = await getMeta();
  return (
    <section id="ozellikler" className="scroll-target space-y-4">
      <h2 className={H2}>Özellikler ve kaynakları</h2>
      <ul className="space-y-1 text-[0.9375rem]">
        {(Object.keys(SOURCE_LABEL) as Source[]).map((s) => (
          <li key={s}>
            <strong>{SOURCE_LABEL[s]}:</strong> {SOURCE_HINT[s]}
          </li>
        ))}
      </ul>
      <div className="space-y-8 pt-2">
        {(Object.keys(GROUP_LABEL) as Group[]).map((g) => (
          <div key={g}>
            <h3 className="display t-sub mb-3 border-b-2 border-ink pb-2 text-ink">{GROUP_LABEL[g]}</h3>
            <dl className="grid gap-x-5 gap-y-2 text-[0.9375rem] sm:grid-cols-[11rem_1fr]">
              {meta.attributes
                .filter((a) => a.group === g)
                .map((a) => (
                  <div key={a.key} className="contents">
                    <dt className="font-semibold text-ink">
                      {a.label}
                      {a.source !== "veri" && <span className="ml-1.5 text-[11px] font-medium text-muted">{SOURCE_LABEL[a.source]}</span>}
                    </dt>
                    <dd className="mb-2 sm:mb-0">{a.hint ? `${a.hint.how}${a.hint.note ? ` ${a.hint.note}` : ""}` : a.description}</dd>
                  </div>
                ))}
            </dl>
          </div>
        ))}
      </div>
    </section>
  );
}
