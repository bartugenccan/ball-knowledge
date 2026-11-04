"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { createStand, standGrid, type StandConfig, type StandHandle } from "./stand-engine";

export type Frame = {
  text: string;
  tone?: "bone" | "hot" | "amber";
  /** Says what the crowd is spelling. Without it a bare name on a stand means nothing. */
  caption?: { kicker: string; main: string; href?: string };
};

const TONE = { bone: 3, hot: 4, amber: 5 } as const;

/** Rasterise a text at stand resolution; a cell is lit if the letter covers it. Needs the page's fonts. */
function bitmap(text: string, vcols: number, rows: number, family: string): Uint8Array {
  const out = new Uint8Array(Math.max(0, vcols * rows));
  if (vcols < 1 || rows < 1) return out;
  const off = document.createElement("canvas");
  off.width = vcols;
  off.height = rows;
  const o = off.getContext("2d", { willReadFrequently: true })!;
  o.font = `900 100px ${family}`;
  const m = o.measureText(text);
  const size = Math.min((100 * vcols * 0.9) / m.width, (100 * rows * 0.8) / (m.actualBoundingBoxAscent + m.actualBoundingBoxDescent));
  o.font = `900 ${size}px ${family}`;
  const m2 = o.measureText(text);
  o.textAlign = "center";
  o.fillText(text, vcols / 2, rows / 2 + (m2.actualBoundingBoxAscent - m2.actualBoundingBoxDescent) / 2);
  const data = o.getImageData(0, 0, vcols, rows).data;
  for (let i = 0; i < out.length; i++) out[i] = data[i * 4 + 3] > 110 ? 1 : 0;
  return out;
}

/**
 * A stand of fans holding up cards, spelling each frame as a wave sweeps across it. Imperfect on
 * purpose, like a real card stunt: some cards are wrong, some people flip late, some seats are
 * empty. The pointer sends a ripple through the crowd.
 *
 * The cards run in a worker (stand.worker.ts) so the wave keeps going while the page is busy.
 */
export function Koreografi({ frames, hold = 3200, staticFrame = 0, className = "" }: { frames: Frame[]; hold?: number; staticFrame?: number; className?: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(0);
  const key = JSON.stringify(frames.map((f) => [f.text, f.tone]));

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const list = JSON.parse(key) as [string, Frame["tone"]][];
    const css = getComputedStyle(el);
    const v = (n: string) => css.getPropertyValue(n).trim();
    const family = v("--font-display") || "sans-serif";
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    // A transferred canvas can never be reused, so each mount makes its own.
    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.cssText = "display:block;width:100%;height:100%";
    el.append(canvas);

    let disposed = false;
    let worker: Worker | undefined;
    let local: StandHandle | undefined;
    let ro: ResizeObserver | undefined;
    let io: IntersectionObserver | undefined;
    let lastPointer = 0;

    const config = (): StandConfig => {
      const r = el.getBoundingClientRect();
      const { vcols, rows } = standGrid(r.width, r.height);
      return {
        width: r.width,
        height: r.height,
        dpr: Math.min(window.devicePixelRatio || 1, 2),
        palette: [v("--stand-seat"), v("--stand-seat-2"), v("--stand-seat-3"), v("--stand-ink"), v("--stand-hot"), v("--stand-amber")],
        tones: list.map(([, tone]) => TONE[tone ?? "bone"]),
        bitmaps: list.map(([text]) => bitmap(text, vcols, rows, family)),
        hold,
        staticFrame: reduce ? staticFrame : null,
      };
    };
    const send = (m: { type: "layout"; cfg: StandConfig } | { type: "pointer"; x: number; y: number; radius: number } | { type: "visible"; on: boolean }) => {
      if (worker) worker.postMessage(m);
      else if (local) {
        if (m.type === "layout") local.layout(m.cfg);
        else if (m.type === "pointer") local.pointer(m.x, m.y, m.radius);
        else local.visible(m.on);
      }
    };
    const onMove = (e: PointerEvent) => {
      const now = performance.now();
      if (now - lastPointer < 45) return;
      lastPointer = now;
      const r = el.getBoundingClientRect();
      send({ type: "pointer", x: e.clientX - r.left, y: e.clientY - r.top, radius: 5 });
    };
    const onDown = (e: PointerEvent) => {
      const r = el.getBoundingClientRect();
      send({ type: "pointer", x: e.clientX - r.left, y: e.clientY - r.top, radius: 26 });
    };

    document.fonts.load(`900 40px ${family}`, list.map(([t]) => t).join("")).finally(() => {
      if (disposed) return;
      const cfg = config();
      if (cfg.width < 1 || cfg.height < 1) return; // hidden Suspense fallback
      if ("transferControlToOffscreen" in canvas && typeof Worker !== "undefined") {
        const off = canvas.transferControlToOffscreen();
        worker = new Worker(new URL("./stand.worker.ts", import.meta.url));
        worker.onmessage = (e: MessageEvent<{ type: string; i: number }>) => {
          if (e.data.type === "frame") setShown(e.data.i);
        };
        worker.postMessage({ type: "init", canvas: off, cfg }, [off]);
      } else {
        local = createStand(canvas, cfg, setShown);
      }
      let w = cfg.width;
      let h = cfg.height;
      ro = new ResizeObserver(() => {
        const r = el.getBoundingClientRect();
        if (Math.abs(r.width - w) < 2 && Math.abs(r.height - h) < 2) return;
        w = r.width;
        h = r.height;
        send({ type: "layout", cfg: config() });
      });
      ro.observe(el);
      if (reduce) return;
      // off screen it costs nothing at all
      io = new IntersectionObserver(([e]) => send({ type: "visible", on: e.isIntersecting }));
      io.observe(el);
      el.addEventListener("pointermove", onMove);
      el.addEventListener("pointerdown", onDown);
    });

    return () => {
      disposed = true;
      ro?.disconnect();
      io?.disconnect();
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerdown", onDown);
      worker?.postMessage({ type: "destroy" });
      local?.destroy();
      canvas.remove();
    };
  }, [key, hold, staticFrame]);

  const caption = frames[shown]?.caption;
  return (
    <div className={`relative h-full w-full overflow-hidden ${className}`}>
      <div ref={host} className="absolute inset-0" />
      {caption && (
        <div className="wrap pointer-events-none absolute inset-x-0 bottom-3 md:bottom-5">
          <div key={caption.kicker + caption.main} className="stand-plate pointer-events-auto inline-block max-w-full">
            <p className="text-xs font-semibold md:text-sm">{caption.kicker}</p>
            {caption.href ? (
              <Link href={caption.href} className="block font-bold underline-offset-4 hover:underline md:text-lg">{caption.main}</Link>
            ) : (
              <p className="font-bold md:text-lg">{caption.main}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
