"use client";

import { Moon, Sun } from "@phosphor-icons/react";

/** Hall lights: the stadium wave passes and the theme changes as it crosses the screen. */
export function ThemeToggle() {
  return (
    <button
      type="button"
      aria-label="Işıkları değiştir"
      title="Işıkları değiştir"
      onClick={() => {
        const root = document.documentElement;
        const nextTheme = root.dataset.theme === "dark" ? "light" : "dark";
        window.dispatchEvent(new Event("bk:wave"));
        setTimeout(() => {
          root.dataset.theme = nextTheme;
          try {
            localStorage.setItem("bk-theme", nextTheme);
          } catch {
            // private mode: the choice just lasts for this page
          }
        }, 260);
      }}
      className="grid h-9 w-9 shrink-0 place-items-center text-ink transition-transform hover:rotate-45 active:scale-90"
    >
      <span className="only-light"><Moon size={20} weight="bold" aria-hidden /></span>
      <span className="only-dark"><Sun size={20} weight="bold" aria-hidden /></span>
    </button>
  );
}
