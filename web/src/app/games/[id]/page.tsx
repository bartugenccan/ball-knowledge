import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";
import { MatchView } from "@/components/match/MatchView";
import { Skeleton } from "@/components/Skeleton";
import { getFixture } from "@/lib/api";
import { seasonLabel } from "@/lib/format";

const WHEN = new Intl.DateTimeFormat("tr-TR", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Istanbul" });

export async function generateMetadata({ params }: PageProps<"/games/[id]">): Promise<Metadata> {
  const { id } = await params;
  const r = await getFixture(id);
  return { title: `${r.home.code} – ${r.away.code}` };
}

export default function GamePage(props: PageProps<"/games/[id]">) {
  return (
    <Suspense fallback={<div className="wrap pt-8"><Skeleton className="h-[800px]" /></div>}>
      <Content {...props} />
    </Suspense>
  );
}

async function Content({ params }: PageProps<"/games/[id]">) {
  const { id } = await params;
  const r = await getFixture(id);
  const rank = (code: string) => {
    const x = r.ranks?.[code];
    return x ? ` (${x.rank}., ${x.wins}-${x.losses})` : "";
  };
  return (
    <div className="wrap space-y-8 pt-8">
      <header className="space-y-2">
        <p className="text-sm text-muted">
          <Link href="/games" className="underline underline-offset-2 hover:text-accent-text">Maçlar</Link>
          {" · "}{seasonLabel(r.season)} · {r.round}. hafta{r.tip_off ? ` · ${WHEN.format(new Date(r.tip_off))}` : ""}
        </p>
        <h1 lang="en" className="display stretch-in text-[clamp(2.2rem,5vw,4.6rem)]">{r.home.name} – {r.away.name}</h1>
        <p className="text-muted">{r.home.code}{rank(r.home.code)} · {r.away.code}{rank(r.away.code)}</p>
        <p className="max-w-[75ch] text-sm text-muted">
          Bu tahmin maçtan önce{r.written_at ? `, ${WHEN.format(new Date(r.written_at))} tarihinde,` : ""} kilitlendi. Kadro son maçlardan tahmin edildi; sakatlık ve maç günü haberleri modelde yok.
        </p>
      </header>
      <MatchView r={r} />
    </div>
  );
}
