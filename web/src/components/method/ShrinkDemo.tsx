"use client";

import { useState } from "react";

const LEAGUE = 0.365;
const K = 400;

/** The small-sample correction, playable: the more attempts, the less the value is pulled to the league rate. */
export function ShrinkDemo() {
  const [att, setAtt] = useState(30);
  const [rate, setRate] = useState(55);
  const makes = Math.round((att * rate) / 100);
  const shrunk = (makes + K * LEAGUE) / (att + K);
  const pos = (v: number) => `${Math.max(0, Math.min(100, ((v - 0.2) / 0.5) * 100))}%`;
  return (
    <figure className="bg-bg-2 p-5 not-prose">
      <figcaption className="display t-sub mb-4 text-ink">Dene: üçlük yüzdesi</figcaption>
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="block space-y-1 text-sm">
          <span className="flex justify-between"><span>Deneme</span><span className="num text-lg text-ink">{att}</span></span>
          <input className="slider" type="range" min={1} max={1000} value={att} onChange={(e) => setAtt(Number(e.target.value))} />
        </label>
        <label className="block space-y-1 text-sm">
          <span className="flex justify-between"><span>Ham yüzde</span><span className="num text-lg text-ink">%{rate}</span></span>
          <input className="slider" type="range" min={20} max={70} value={rate} onChange={(e) => setRate(Number(e.target.value))} />
        </label>
      </div>
      <div className="relative mb-7 mt-10 h-10 border-b-2 border-ink" aria-hidden>
        <Pin left={pos(LEAGUE)} label={`Lig ${tr(LEAGUE * 100)}`} color="var(--dim)" below />
        <Pin left={pos(rate / 100)} label="Ham" color="var(--muted)" below />
        <Pin left={pos(shrunk)} label="Puana giren" color="var(--accent)" thick />
      </div>
      <p className="text-sm" aria-live="polite">
        {att} denemede {makes} isabet. Düzeltilmiş değer <strong className="num text-xl text-accent-text">{tr(shrunk * 100)}</strong>
      </p>
    </figure>
  );
}

const tr = (v: number) => `%${v.toFixed(1).replace(".", ",")}`;

/** The animated value labels itself above the line; the fixed references sit below it. */
function Pin({ left, label, color, thick, below }: { left: string; label: string; color: string; thick?: boolean; below?: boolean }) {
  return (
    <span className="absolute bottom-0 transition-[left] duration-500 ease-[cubic-bezier(0.3,1.5,0.5,1)]" style={{ left }}>
      <span className="block" style={{ width: thick ? 6 : 3, height: thick ? 40 : 22, background: color, marginLeft: thick ? -3 : -1.5 }} />
      <span className={`absolute left-0 -translate-x-1/2 whitespace-nowrap text-[11px] font-semibold text-ink ${below ? "-bottom-5" : "-top-5"}`}>{label}</span>
    </span>
  );
}
