import { FlipLink } from "@/components/Flip";
import { Koreografi } from "@/components/motion/Koreografi";

export default function NotFound() {
  return (
    <div>
      <div className="on-stand h-[44dvh] min-h-[240px] max-h-[460px]">
        <Koreografi frames={[{ text: "404", tone: "hot" }]} />
      </div>
      <div className="wrap space-y-5 pt-8">
        <h1 className="display t-page stretch-in">Top dışarıda</h1>
        <p className="max-w-[50ch] text-lg text-muted">Aradığın sayfa ya da oyuncu burada değil. Bu sezon oynamamış olabilir.</p>
        <FlipLink href="/players">Oyuncuları incele</FlipLink>
      </div>
    </div>
  );
}
