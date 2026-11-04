"use client";

import { FlipButton } from "@/components/Flip";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="wrap space-y-5 pt-16">
      <h1 className="display t-page stretch-in">Mola</h1>
      <p className="max-w-[56ch] text-lg text-muted">
        Veriye ulaşamadık. Puan motoru çalışmıyor olabilir: yerelde <code className="bg-bg-2 px-1.5 py-0.5 font-mono text-[0.9em] text-ink">npm run dev</code> ile ikisini birlikte başlatabilirsin.
      </p>
      <FlipButton type="button" onClick={reset}>Tekrar dene</FlipButton>
    </div>
  );
}
