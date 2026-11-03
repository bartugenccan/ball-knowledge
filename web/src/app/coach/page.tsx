import type { Metadata } from "next";
import { Simulator } from "@/components/coach/Simulator";

export const metadata: Metadata = { title: "Koç Paneli" };

export default function CoachPage() {
  return (
    <div className="space-y-6">
      <header className="space-y-2">
        <h1 className="font-display text-5xl font-extrabold uppercase tracking-tight">Set simülatörü</h1>
        <p className="max-w-[70ch] text-muted">
          Bir set seç, hücum ve savunma beşlisini yerleştir. Simülatör seti binlerce kez oynatır. Dalların olasılığı oyuncu puanlarına,
          şutun boş ya da contest edilmiş olması savunmacıya, isabet ise yorgunluğa ve clutch durumuna göre değişir.
        </p>
      </header>
      <Simulator />
    </div>
  );
}
