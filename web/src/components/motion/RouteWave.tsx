"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";
import { allClubColors } from "@/lib/clubs";

/**
 * Route transition: a stadium wave in every club's colours passes over the page. It runs in a worker, so a heavy page
 * mounting underneath cannot freeze it, and it never delays the navigation. The theme toggle
 * fires the same wave through the "bk:wave" event.
 */
export function RouteWave() {
  const path = usePathname();
  const host = useRef<HTMLDivElement>(null);
  const lastPath = useRef(path);
  const play = useRef<() => void>(() => {});

  useEffect(() => {
    const el = host.current;
    if (!el || !("transferControlToOffscreen" in HTMLCanvasElement.prototype)) return; // no wave is a fine fallback
    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.cssText = "display:block;width:100%;height:100%";
    canvas.width = 1;
    canvas.height = 1;
    el.append(canvas);
    const off = canvas.transferControlToOffscreen();
    const worker = new Worker(new URL("./wave.worker.ts", import.meta.url));
    worker.postMessage({ type: "init", canvas: off, colors: allClubColors() }, [off]);
    play.current = () => {
      if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      worker.postMessage({ type: "play", width: window.innerWidth, height: window.innerHeight, dpr: Math.min(window.devicePixelRatio || 1, 2) });
    };
    const onWave = () => play.current();
    window.addEventListener("bk:wave", onWave);
    return () => {
      play.current = () => {};
      window.removeEventListener("bk:wave", onWave);
      worker.terminate();
      canvas.remove();
    };
  }, []);

  useEffect(() => {
    if (lastPath.current === path) return;
    lastPath.current = path;
    play.current();
  }, [path]);

  return <div ref={host} aria-hidden className="pointer-events-none fixed inset-0 z-50" />;
}
