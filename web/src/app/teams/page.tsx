import type { Metadata } from "next";
import { Suspense } from "react";
import { Skeleton } from "@/components/Skeleton";
import { TeamsBoard } from "@/components/TeamsBoard";
import { getMeta, getTeams } from "@/lib/api";
import { seasonLabel } from "@/lib/format";

export const metadata: Metadata = { title: "Takımlar" };

export default function TeamsPage({ searchParams }: PageProps<"/teams">) {
  return (
    <div className="wrap space-y-5 pt-8">
      <h1 className="display t-page stretch-in">Takımlar</h1>
      <Suspense fallback={<Skeleton className="h-[600px]" />}>
        <TeamsTable searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

async function TeamsTable({ searchParams }: { searchParams: PageProps<"/teams">["searchParams"] }) {
  const sp = await searchParams;
  const meta = await getMeta();
  const season = typeof sp.season === "string" ? sp.season : meta.latest;
  const { teams } = await getTeams(season);
  return (
    <>
      <p className="max-w-[70ch] text-muted">{seasonLabel(season)} sezonu, rotasyon oyuncularının ortalama özellikleri. Renk, takımlar arasındaki sırayı gösterir. Bir sütuna tıkla, tablo yeniden dizilsin.</p>
      <TeamsBoard teams={teams} season={season} />
    </>
  );
}
