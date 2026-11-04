"use client";

import { useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

const STEP_MS = 95;

/**
 * Split-flap scoreboard number. Each digit clatters through the values on its way to the
 * target, and a new value flips on from the old one (the simulator's PPP re-runs do this).
 */
export function Flap({ value, decimals = 0, className = "", size, bg, ink }: { value: number; decimals?: number; className?: string; size?: string; bg?: string; ink?: string }) {
  const text = value.toFixed(decimals);
  const rootRef = useRef<HTMLSpanElement>(null);
  const [armed, setArmed] = useState(false);
  const reduce = useReducedMotion();

  useEffect(() => {
    const el = rootRef.current;
    if (!el || reduce) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting) return;
        setArmed(true);
        io.disconnect();
      },
      { threshold: 0.4 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [reduce]);

  return (
    <span ref={rootRef} role="img" aria-label={text} className={`flap ${className}`} style={{ ...(size ? { "--size": size } : {}), ...(bg ? { "--flap-bg": bg } : {}), ...(ink ? { "--flap-ink": ink } : {}) } as React.CSSProperties}>
      {[...text].map((ch, i) =>
        /\d/.test(ch) ? (
          <FlapDigit key={`${text.length}-${i}`} digit={Number(ch)} armed={armed} lag={i * 2} />
        ) : (
          <span key={`${text.length}-${i}`} aria-hidden className="flap-sep">{ch}</span>
        ),
      )}
    </span>
  );
}

function FlapDigit({ digit, armed, lag }: { digit: number; armed: boolean; lag: number }) {
  // shown === null: never started, so server and first client paint show the final digit
  const [shown, setShown] = useState<number | null>(null);
  const current = shown ?? digit;

  useEffect(() => {
    if (!armed) return;
    if (shown === null) {
      const t = setTimeout(() => setShown(0), lag * STEP_MS);
      return () => clearTimeout(t);
    }
    if (shown === digit) return;
    const t = setTimeout(() => setShown((shown + 1) % 10), STEP_MS);
    return () => clearTimeout(t);
  }, [armed, shown, digit, lag]);

  const prev = (current + 9) % 10;
  const moving = shown !== null;
  return (
    <span aria-hidden className="flap-d">
      {/* resting halves: new digit on top, old digit below until the flap lands */}
      <span className="flap-h flap-t"><b>{current}</b></span>
      <span className="flap-h flap-b"><b>{moving && shown !== digit ? prev : current}</b></span>
      {moving && (
        <span key={current}>
          <span className="flap-h flap-t flap-out"><b>{prev}</b></span>
          <span className="flap-h flap-b flap-in"><b>{current}</b></span>
        </span>
      )}
    </span>
  );
}
