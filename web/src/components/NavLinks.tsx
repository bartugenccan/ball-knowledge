"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/players", label: "Oyuncular" },
  { href: "/teams", label: "Takımlar" },
  { href: "/compare", label: "Karşılaştır" },
  { href: "/coach", label: "Koç Paneli" },
  { href: "/method", label: "Yöntem" },
];

/** Primary nav; the active pill slides between items (shared layoutId). */
export function NavLinks(props: { static?: boolean }) {
  return props.static ? <Links path="" /> : <ActiveLinks />;
}

function ActiveLinks() {
  return <Links path={usePathname()} />;
}

function Links({ path }: { path: string }) {
  return (
    <nav className="-mx-1 flex min-w-0 gap-1 overflow-x-auto text-sm">
      {NAV.map((n) => {
        const active = path === n.href || path.startsWith(`${n.href}/`);
        return (
          <Link
            key={n.href}
            href={n.href}
            className={`relative isolate whitespace-nowrap rounded-full px-3 py-1.5 transition-colors ${active ? "text-ink" : "text-muted hover:text-ink"}`}
          >
            {active && (
              <motion.span
                layoutId="nav-active"
                className="absolute inset-0 -z-10 rounded-full bg-panel-2 ring-1 ring-line-2"
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              />
            )}
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}
