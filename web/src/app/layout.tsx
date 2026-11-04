import type { Metadata } from "next";
import { Sofia_Sans, Sofia_Sans_Condensed } from "next/font/google";
import Link from "next/link";
import { Suspense } from "react";
import { MotionProvider } from "@/components/motion/MotionProvider";
import { RouteWave } from "@/components/motion/RouteWave";
import { NavLinks } from "@/components/NavLinks";
import { ThemeToggle } from "@/components/ThemeToggle";
import "./globals.css";

const display = Sofia_Sans_Condensed({ variable: "--font-display", subsets: ["latin", "latin-ext"] });
const body = Sofia_Sans({ variable: "--font-body", subsets: ["latin", "latin-ext"] });

export const metadata: Metadata = {
  title: { default: "Ball Knowledge", template: "%s | Ball Knowledge" },
  description: "EuroLeague oyuncuları için 1-20 özellik puanları, form takibi ve koçlar için set simülasyonu.",
};

// Runs before first paint so the page never flashes the wrong theme.
const BOOT = `(function(){var d=document.documentElement;d.classList.add("js");try{d.dataset.theme=localStorage.getItem("bk-theme")||(matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light")}catch(e){d.dataset.theme="light"}})()`;

// A "B" held up in cards.
const LOGO = ["11110", "10001", "11110", "10001", "11110"];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="tr" suppressHydrationWarning className={`${display.variable} ${body.variable} h-full antialiased`}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: BOOT }} />
      </head>
      <body className="flex min-h-full flex-col">
        <MotionProvider>
          <header className="sticky top-0 z-30 border-b-[3px] border-ink bg-bg">
            <div className="wrap flex h-16 items-center gap-5 md:gap-8">
              <Link href="/" className="flex shrink-0 items-center gap-2.5" aria-label="Ball Knowledge ana sayfa">
                <span aria-hidden className="logo-mark">
                  {LOGO.flatMap((row, r) =>
                    [...row].map((c, x) => <i key={`${r}${x}`} className={c === "1" ? "on" : undefined} style={{ ["--d" as string]: r + x }} />),
                  )}
                </span>
                <span className="display hidden text-2xl sm:block">Ball Knowledge</span>
              </Link>
              {/* usePathname is request data: stream the active state, show plain links meanwhile */}
              <Suspense fallback={<NavLinks static />}>
                <NavLinks />
              </Suspense>
              <div className="ml-auto">
                <ThemeToggle />
              </div>
            </div>
          </header>
          <main className="w-full flex-1">{children}</main>
          <footer className="on-stand mt-20 overflow-hidden pt-8">
            <div className="wrap flex flex-wrap items-end justify-between gap-4 pb-6">
              <p className="max-w-[58ch] text-sm text-muted">
                Veri: EuroLeague açık istatistik uçları. Ticari olmayan prototip, EuroLeague ile bağlantılı değildir.
              </p>
              <Link href="/method" className="text-sm font-semibold underline underline-offset-4 hover:text-accent-text">Puanlar nasıl hesaplanıyor?</Link>
            </div>
            <p aria-hidden className="display select-none whitespace-nowrap text-center text-[17.4vw]" style={{ lineHeight: 0.74 }}>Ball Knowledge</p>
          </footer>
          <Suspense fallback={null}>
            <RouteWave />
          </Suspense>
        </MotionProvider>
      </body>
    </html>
  );
}
