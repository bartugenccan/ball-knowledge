import type { Metadata } from "next";
import { Simulator } from "@/components/coach/Simulator";

export const metadata: Metadata = { title: "Koç Paneli" };

export default function CoachPage() {
  return (
    <div className="wrap space-y-6 pt-8">
      <header className="space-y-3">
        <h1 className="display t-page stretch-in">Set simülatörü</h1>
        <p className="max-w-[70ch] text-muted">
          Bir set seç, hücum ve savunma beşlisini yerleştir. Simülatör seti binlerce kez oynatır. Dalların olasılığı oyuncu puanlarına,
          şutun boş ya da contest edilmiş olması savunmacıya, isabet ise yorgunluğa ve clutch durumuna göre değişir.
        </p>
      </header>
      <Simulator />
    </div>
  );
}
