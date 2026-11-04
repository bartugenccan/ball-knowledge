"use client";

import { useCallback, useLayoutEffect, useRef, type RefObject } from "react";

/**
 * League-table shuffle: when the order changes, rows on screen slide from their old position
 * to the new one (FLIP with the Web Animations API, nothing goes through React state).
 * Rows that are off screen are skipped, so a 240-row table stays cheap.
 */
export function useRowFlip(orderKey: string, scroller?: RefObject<HTMLElement | null>) {
  const rows = useRef(new Map<string, HTMLElement>());
  const prev = useRef(new Map<string, number>());

  const register = useCallback(
    (id: string) => (el: HTMLElement | null) => {
      if (el) rows.current.set(id, el);
      else rows.current.delete(id);
    },
    [],
  );

  useLayoutEffect(() => {
    const next = new Map<string, number>();
    rows.current.forEach((el, id) => next.set(id, el.offsetTop));
    if (prev.current.size && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const box = scroller?.current?.getBoundingClientRect();
      const top = box ? box.top : 0;
      const bottom = box ? box.bottom : window.innerHeight;
      let n = 0;
      rows.current.forEach((el, id) => {
        const from = prev.current.get(id);
        const to = next.get(id);
        if (from === undefined || to === undefined || from === to) return;
        const r = el.getBoundingClientRect();
        if (r.bottom < top || r.top > bottom) return;
        const dy = Math.max(-640, Math.min(640, from - to));
        el.animate([{ transform: `translateY(${dy}px)` }, { transform: "none" }], {
          duration: 560,
          delay: Math.min(n++, 24) * 9,
          easing: "cubic-bezier(0.2, 1.15, 0.35, 1)",
          fill: "backwards",
        });
      });
    }
    prev.current = next;
  }, [orderKey, scroller]);

  return register;
}
