"use client";

import { useEffect, useRef, type CSSProperties, type ReactNode } from "react";

/**
 * Flips data-seen when the element reaches the viewport. CSS entry animations stay paused
 * until then (see globals.css), so charts run their entrance when you can actually see it.
 */
export function InView({ children, className, style, amount = 0.2 }: { children: ReactNode; className?: string; style?: CSSProperties; amount?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting) return;
        el.dataset.seen = "true";
        io.disconnect();
      },
      { threshold: amount },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [amount]);
  return (
    <div ref={ref} data-seen="false" className={className} style={style}>
      {children}
    </div>
  );
}
