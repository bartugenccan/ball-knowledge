"use client";

import { ArrowCounterClockwise } from "@phosphor-icons/react";
import { useEffect, useRef, useState } from "react";
import { COURT_H, COURT_W, CourtLines, tx, ty } from "@/components/Court";
import type { Shot } from "@/lib/types";

const STAGGER = 7; // ms between shots
const FLIGHT = 520;

/**
 * Season replay: every shot flies at the rim, then stamps its spot. Made = a dot in the club's colour,
 * missed = a grey cross. One canvas instead of hundreds of animated SVG nodes, and it stops drawing when done.
 */
export function ShotChart({ shots }: { shots: Shot[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [run, setRun] = useState(0);
  const made = shots.filter((s) => s.made).length;

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    const pts = shots
      .filter((s) => ty(s.y) < COURT_H)
      .map((s, i) => {
        const x0 = tx(s.x);
        const y0 = ty(s.y);
        const x1 = tx(0);
        const y1 = ty(0);
        // bow the path a little so a season of shots reads as ball flight, not a star of lines
        return { x0, y0, x1, y1, cx: (x0 + x1) / 2 + (y1 - y0) * 0.14, cy: (y0 + y1) / 2 + (x0 - x1) * 0.14, made: s.made, at: Math.min(i, 200) * STAGGER };
      });
    const total = (pts.at(-1)?.at ?? 0) + FLIGHT + 300;
    let raf = 0;
    let colors = { hot: "", cold: "", court: "" };
    let k = 1;

    const readColors = () => {
      const css = getComputedStyle(canvas);
      colors = { hot: css.getPropertyValue("--club-show").trim(), cold: css.getPropertyValue("--muted").trim(), court: css.getPropertyValue("--court").trim() };
    };
    const fit = () => {
      const r = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(r.width * dpr));
      canvas.height = Math.max(1, Math.round(r.height * dpr));
      k = canvas.width / COURT_W;
    };
    const stamp = (p: (typeof pts)[number], scale: number) => {
      const x = p.x0 * k;
      const y = p.y0 * k;
      if (p.made) {
        ctx.beginPath();
        ctx.arc(x, y, 16 * k * scale, 0, Math.PI * 2);
        ctx.fillStyle = colors.hot;
        ctx.fill();
        ctx.lineWidth = 3 * k;
        ctx.strokeStyle = colors.court;
        ctx.stroke();
      } else {
        const a = 11 * k * scale;
        ctx.lineWidth = 7 * k;
        ctx.lineCap = "square";
        ctx.strokeStyle = colors.cold;
        ctx.beginPath();
        ctx.moveTo(x - a, y - a);
        ctx.lineTo(x + a, y + a);
        ctx.moveTo(x - a, y + a);
        ctx.lineTo(x + a, y - a);
        ctx.stroke();
      }
    };
    const draw = (t: number) => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      for (const p of pts) {
        const q = (t - p.at) / FLIGHT;
        if (q <= 0) continue;
        if (q < 1) {
          // a short comet running along the curve
          ctx.beginPath();
          ctx.lineWidth = 4 * k;
          ctx.lineCap = "round";
          ctx.strokeStyle = p.made ? colors.hot : colors.cold;
          for (let i = 0; i <= 6; i++) {
            const u = Math.max(0, q - 0.16 + (i / 6) * 0.16);
            const x = (1 - u) ** 2 * p.x0 + 2 * (1 - u) * u * p.cx + u ** 2 * p.x1;
            const y = (1 - u) ** 2 * p.y0 + 2 * (1 - u) * u * p.cy + u ** 2 * p.y1;
            if (i) ctx.lineTo(x * k, y * k);
            else ctx.moveTo(x * k, y * k);
          }
          ctx.stroke();
        }
        if (q > 0.75) {
          const e = Math.min(1, (q - 0.75) / 0.5);
          stamp(p, 1 + (1 - e) * 1.2); // lands big, settles
        }
      }
    };

    let started = false;
    const start = () => {
      if (started) return;
      started = true;
      readColors();
      fit();
      if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
        draw(Infinity);
        return;
      }
      const t0 = performance.now();
      const frame = (now: number) => {
        const t = now - t0;
        draw(t);
        if (t < total) raf = requestAnimationFrame(frame);
        else draw(Infinity);
      };
      raf = requestAnimationFrame(frame);
    };
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting) return;
        io.disconnect();
        start();
      },
      { threshold: 0.25 },
    );
    io.observe(canvas);
    const ro = new ResizeObserver(() => {
      if (!started) return;
      fit();
      draw(Infinity);
    });
    ro.observe(canvas);
    const theme = new MutationObserver(() => {
      if (!started) return;
      readColors();
      draw(Infinity);
    });
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      ro.disconnect();
      theme.disconnect();
    };
  }, [shots, run]);

  return (
    <figure>
      <div className="relative">
        <svg viewBox={`0 0 ${COURT_W} ${COURT_H}`} className="block w-full bg-[var(--court)]" role="img" aria-label={`Şut haritası: ${shots.length} şut, ${made} isabet`}>
          <CourtLines stroke="var(--court-line)" rim="var(--accent)" paint="var(--panel)" />
        </svg>
        <canvas ref={canvasRef} aria-hidden className="pointer-events-none absolute inset-0 h-full w-full" />
        <button
          type="button"
          onClick={() => setRun((n) => n + 1)}
          className="absolute right-2 top-2 flex items-center gap-1.5 bg-ink px-2.5 py-1.5 text-xs font-semibold text-bg transition-transform hover:-translate-y-0.5 active:translate-y-0"
        >
          <ArrowCounterClockwise size={14} weight="bold" aria-hidden />
          Tekrar oynat
        </button>
      </div>
      <figcaption className="flex gap-5 pt-2 text-xs text-muted">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: "var(--club-show)" }} /> İsabet {made}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="font-bold" style={{ color: "var(--muted)" }}>✕</span> Kaçan {shots.length - made}
        </span>
      </figcaption>
    </figure>
  );
}
