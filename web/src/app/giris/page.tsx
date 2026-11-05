import type { Metadata } from "next";
import { Suspense } from "react";
import { safeNext } from "@/lib/gate";

export const metadata: Metadata = { title: "Giriş" };

function Fields({ next, wrong }: { next: string; wrong: boolean }) {
  return (
    <form method="post" action="/giris/gonder" className="space-y-3">
      <input type="hidden" name="next" value={next} />
      <label className="block space-y-1.5">
        <span className="text-sm font-semibold">Şifre</span>
        <input
          type="password" name="password" required autoFocus autoComplete="current-password"
          aria-invalid={wrong} aria-describedby={wrong ? "gate-error" : undefined}
          className="block w-full rounded-md border border-line bg-bg px-3 py-2.5 text-base"
        />
      </label>
      {wrong && <p id="gate-error" role="alert" className="text-sm font-semibold">Şifre yanlış, tekrar dene.</p>}
      <button type="submit" className="w-full rounded-md bg-ink px-4 py-2.5 font-semibold text-bg">Giriş yap</button>
    </form>
  );
}

async function GateForm({ searchParams }: { searchParams: PageProps<"/giris">["searchParams"] }) {
  const { next, hata } = await searchParams;
  return <Fields next={safeNext(next)} wrong={hata === "1"} />;
}

export default function GatePage({ searchParams }: PageProps<"/giris">) {
  return (
    <div className="wrap pt-12">
      <div className="max-w-sm space-y-5">
        <h1 className="display t-page stretch-in">Giriş</h1>
        <p className="text-muted">Site şimdilik yalnızca test ekibine açık. Sana verilen şifreyi gir.</p>
        <Suspense fallback={<Fields next="/" wrong={false} />}>
          <GateForm searchParams={searchParams} />
        </Suspense>
      </div>
    </div>
  );
}
