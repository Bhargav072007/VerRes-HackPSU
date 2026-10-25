import type { Metadata } from "next";
import { Inter, Source_Serif_4 } from "next/font/google";
import Link from "next/link";
import { ArrowUpRight, BookOpen } from "lucide-react";
import { Providers } from "@/components/providers";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const serif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-source-serif",
});
export const metadata: Metadata = {
  title: "VerRes — proof, not vibes",
  openGraph: {
    title: "VerRes — proof, not vibes",
    description: "A pre-submission integrity review for research papers. Every finding carries a receipt.",
    siteName: "VerRes",
    type: "website",
  },
  twitter: { card: "summary", title: "VerRes — proof, not vibes" },
  description:
    "A pre-submission integrity review for research papers. Every finding carries a receipt.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${serif.variable}`}>
      <body className="flex min-h-dvh flex-col font-sans antialiased">
        <Providers>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-3"
          >
            Skip to content
          </a>
          <header className="mx-auto flex h-20 w-full max-w-6xl items-center justify-between border-b px-6 md:px-10">
            <Link
              href="/"
              aria-label="VerRes home"
              className="flex items-center gap-3"
            >
              <span className="flex size-8 items-center justify-center rounded-md border bg-white">
                <BookOpen size={18} strokeWidth={1.6} />
              </span>
              <span className="text-xl font-semibold tracking-tight">
                VerRes
                <span className="ml-2 align-top text-[9px] font-normal tracking-widest text-muted-foreground">
                  BETA
                </span>
              </span>
            </Link>
            <Link
              href="/#how-it-works"
              className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground"
            >
              How it works <ArrowUpRight size={14} />
            </Link>
          </header>
          {children}
          <footer className="mx-auto mt-auto flex w-full max-w-6xl flex-col gap-3 border-t px-6 py-6 text-[11px] text-muted-foreground sm:flex-row sm:items-center sm:justify-between md:px-10">
            <span>VerRes · Research deserves a second look.</span>
            <span className="tracking-[.13em] uppercase">
              Receipts, not scores.
            </span>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
