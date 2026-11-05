"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

const NAV = [
  { href: "/players", label: "Oyuncular" },
  { href: "/teams", label: "Takımlar" },
  { href: "/games", label: "Maçlar" },
  { href: "/standings", label: "Puan Durumu" },
  { href: "/compare", label: "Karşılaştır" },
  { href: "/coach", label: "Koç Paneli" },
  { href: "/method", label: "Yöntem" },
];

/** Primary nav. Labels are squeezed until you point at them, the current page stays wide. */
export function NavLinks(props: { static?: boolean }) {
  return props.static ? <Links path="" /> : <ActiveLinks />;
}

function ActiveLinks() {
  const path = usePathname();
  useEffect(() => {
    document.querySelector('nav[aria-label="Ana menü"] [aria-current="page"]')?.scrollIntoView({ inline: "center", block: "nearest" });
  }, [path]);
  return <Links path={path} />;
}

function Links({ path }: { path: string }) {
  return (
    <nav className="-mx-1 flex min-w-0 items-center gap-3 overflow-x-auto px-1 md:gap-4" aria-label="Ana menü">
      {NAV.map((n) => {
        const active = path === n.href || path.startsWith(`${n.href}/`);
        return (
          <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined} className="nav-link">
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}
