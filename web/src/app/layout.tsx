import type { Metadata } from "next";
import { Barlow_Condensed, Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { Suspense } from "react";
import { MotionProvider } from "@/components/motion/MotionProvider";
import { NavLinks } from "@/components/NavLinks";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin", "latin-ext"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const display = Barlow_Condensed({
  variable: "--font-display",
  subsets: ["latin", "latin-ext"],
  weight: ["500", "600", "700", "800"],
});

export const metadata: Metadata = {
  title: { default: "Ball Knowledge", template: "%s · Ball Knowledge" },
  description: "EuroLeague oyuncuları için 1–20 özellik puanları, form takibi ve koçlar için set simülasyonu.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="tr" className={`${geistSans.variable} ${geistMono.variable} ${display.variable} h-full antialiased`}>
      <body className="flex min-h-full flex-col">
        <header className="sticky top-0 z-30 border-b border-line/70 bg-bg/70 backdrop-blur-xl">
          <div className="mx-auto flex h-16 max-w-7xl items-center gap-6 px-4">
            <Link href="/" className="group flex shrink-0 items-center gap-2.5">
              <span
                aria-hidden
                className="grid h-8 w-8 place-items-center rounded-full bg-accent font-display text-sm font-bold text-accent-ink transition-transform duration-300 group-hover:rotate-[20deg]"
              >
                BK
              </span>
              <span className="font-display text-xl font-bold uppercase tracking-wide">Ball Knowledge</span>
            </Link>
            {/* usePathname is request data: stream the active state, show plain links meanwhile */}
            <Suspense fallback={<NavLinks static />}>
              <NavLinks />
            </Suspense>
          </div>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8">
          <MotionProvider>{children}</MotionProvider>
        </main>
        <footer className="border-t border-line/70 px-4 py-6 text-center text-xs text-dim">
          Veri: EuroLeague açık istatistik uçları. Ticari olmayan prototip, EuroLeague ile bağlantılı değildir.
        </footer>
      </body>
    </html>
  );
}
