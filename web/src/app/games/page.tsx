import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { Skeleton } from "@/components/Skeleton";
import { getFixtures } from "@/lib/api";
import { clubPair } from "@/lib/clubs";
import type { FixtureCard, FixturesOverview } from "@/lib/match";

export const metadata: Metadata = { title: "Maçlar" };

const WHEN = new Intl.DateTimeFormat("tr-TR", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Istanbul" });
const percent = (x: number) => `%${Math.round(100 * x)}`;

export default function GamesPage() {
  return (
    <div className="wrap space-y-12 pt-8">
      <header className="space-y-3">
        <h1 className="display t-page stretch-in">Maçlar</h1>
        <p className="max-w-[70ch] text-muted">
          Fikstürdeki her maç, oynanmadan önce oyuncuların puanları ve takımların oyun tarzıyla baştan sona oynatılıyor. Bir maç aç: nerede kim avantajlı, maç nasıl akar, koç neye bakmalı.
        </p>
      </header>
      <Suspense fallback={<Skeleton className="h-[600px]" />}>
        <Content />
      </Suspense>
    </div>
  );
}

async function Content() {
  const data = await getFixtures();
  const upcoming = data.games.filter((g) => g.status === "upcoming");
  const played = data.games.filter((g) => g.status === "played").reverse();
  const rounds = [...new Set(upcoming.map((g) => g.round))];
  return (
    <>
      {rounds.map((round) => (
        <section key={round} className="space-y-4">
          <h2 className="display t-sec">{round}. hafta</h2>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {upcoming.filter((g) => g.round === round).map((g) => <Card key={g.id} g={g} />)}
          </div>
        </section>
      ))}
      {played.length > 0 && (
        <section className="space-y-4">
          <h2 className="display t-sec">Biz böyle dedik, gerçekte böyle oldu</h2>
          <p className="max-w-[70ch] text-muted">Tahminler maçtan önce kilitlendi, sonradan değiştirilmedi. Tutmayanlar da burada.</p>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {played.map((g) => <Card key={g.id} g={g} />)}
          </div>
        </section>
      )}
      <Reliability data={data} />
    </>
  );
}

function Rank({ r }: { r?: { rank: number; wins: number; losses: number } | null }) {
  return r ? <span className="text-xs font-normal text-muted">{r.rank}. ({r.wins}-{r.losses})</span> : null;
}

function Card({ g }: { g: FixtureCard }) {
  const score = (s: number[]) => (
    <span className="num text-2xl">
      <span style={{ color: "var(--side-a-t)" }}>{s[0]}</span>
      <span className="mx-1 text-base text-dim">–</span>
      <span style={{ color: "var(--side-b-t)" }}>{s[1]}</span>
    </span>
  );
  return (
    <Link href={`/games/${g.id}`} prefetch={false} className="pair group flex flex-col gap-2 rounded-md border border-line p-4 transition-colors hover:border-ink" style={clubPair(g.home.code, g.away.code)}>
      <p className="text-xs text-muted">{g.tip_off ? WHEN.format(new Date(g.tip_off)) : `${g.round}. hafta`}</p>
      <div lang="en" className="font-semibold group-hover:underline">
        <p className="flex items-baseline justify-between gap-2"><span className="truncate">{g.home.name}</span><Rank r={g.ranks[g.home.code]} /></p>
        <p className="flex items-baseline justify-between gap-2"><span className="truncate">{g.away.name}</span><Rank r={g.ranks[g.away.code]} /></p>
      </div>
      {g.real && <p className="flex items-baseline justify-between"><span className="text-sm text-muted">Gerçek</span>{score(g.real)}</p>}
      <p className="flex items-baseline justify-between"><span className="text-sm text-muted">En olası senaryo</span>{score(g.typical)}</p>
      {g.status === "played" ? (
        <p className="text-xs text-muted">{g.favored_won ? "Kazanan doğru" : "Kazanan yanlış"}, skor farkı {g.margin_in_range ? "beklenen aralıkta" : "aralığın dışında"}</p>
      ) : (
        <p className="line-clamp-3 text-sm text-muted">{g.headline}</p>
      )}
    </Link>
  );
}

function Reliability({ data }: { data: FixturesOverview }) {
  const { record: r, history: h } = data;
  const past = h.likely ?? h.known;
  const facts: [string, string][] = past ? [
    ["Geri dönük maç", String(past.games)],
    ["Kazanan isabeti", percent(past.winner)],
    ["Skor farkı hatası", `${past.margin_error.toFixed(1)} sayı`],
    ["Fark %80 aralıkta", percent(past.margin_in_range)],
    ["Toplam skor %80 aralıkta", percent(past.total_in_range)],
  ] : [];
  return (
    <section className="space-y-4">
      <h2 className="display t-sec">Ne kadar güvenilir?</h2>
      <p className="max-w-[75ch] text-muted">
        Tek bir maç çoğunlukla şanstır: en iyi model bile her on maçtan birini 20 sayı ıskalar. Asıl değer kazananı bilmekte değil, maçın nasıl geçeceğini anlatmakta.
      </p>
      {r.games > 0 ? (
        <p className="max-w-[75ch]">
          <span className="font-semibold">Kilitli tahminler:</span> {r.games} maçta kazanan {percent(r.winner ?? 0)}, skor farkı hatası {(r.margin_error ?? 0).toFixed(1)} sayı, fark {percent(r.margin_in_range ?? 0)} aralıkta. Gerçek sınav bu; 50 maçtan önce rakamlar çok oynar.
        </p>
      ) : (
        <p className="max-w-[75ch]"><span className="font-semibold">Kilitli tahminler:</span> ilk maçların sonucu bekleniyor. Gerçek sınav bu olacak.</p>
      )}
      {past && (
        <>
          <dl className="grid max-w-4xl grid-cols-2 gap-x-8 gap-y-3 md:grid-cols-3">
            {facts.map(([k, v]) => (
              <div key={k} className="border-t border-line pt-1">
                <dt className="text-xs text-muted">{k}</dt>
                <dd className="num text-2xl">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="max-w-[75ch] text-xs text-dim">
            Geri dönük rakamlar geçmiş maçları kendi tarihinden önceki veriyle ve kadroyu son maçlardan tahmin ederek oynatır. Ayarlar bu maçlarda seçildiği için iyimserdir. Kazananı tahminde basit takım net reytingiyle başa baş (log-kayıp {past.log_loss.toFixed(3)} ve {past.net_rating_loss.toFixed(3)}).
            Model; kimin kimi savunduğunu, set çeşitlerini, maç günü sakatlıklarını bilmez.
          </p>
        </>
      )}
    </section>
  );
}
