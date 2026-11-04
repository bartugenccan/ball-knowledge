"use client";

import { useEffect, useRef } from "react";

const DIGITS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];

/**
 * Odometer: each digit is a strip that rolls to its value, right-hand digits last.
 * Server markup already holds the final value; this only arms the roll when it scrolls in.
 */
export function Odo({ value, decimals = 0, suffix = "", className = "" }: { value: number; decimals?: number; suffix?: string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const text = value.toFixed(decimals);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    el.dataset.armed = "false";
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting) return;
        void el.offsetWidth; // commit the zero position before the transition starts
        el.dataset.armed = "true";
        io.disconnect();
      },
      { threshold: 0.3 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <span ref={ref} role="img" aria-label={`${text}${suffix}`} className={`odo ${className}`}>
      {[...text].map((ch, i) =>
        /\d/.test(ch) ? (
          <span key={`${text.length}-${i}`} aria-hidden className="odo-col" style={{ width: "0.54em" }}>
            <span style={{ ["--d" as string]: Number(ch), ["--i" as string]: i }}>
              {DIGITS.map((d) => <b key={d}>{d}</b>)}
            </span>
          </span>
        ) : (
          <span key={`${text.length}-${i}`} aria-hidden>{ch}</span>
        ),
      )}
      {suffix && <span aria-hidden>{suffix}</span>}
    </span>
  );
}
