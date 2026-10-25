import type { Metadata } from "next";
import { Inter, Source_Serif_4, Sora } from "next/font/google";
import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Providers } from "@/components/providers";
import "./globals.css";
import { Brand } from "@/components/brand";

const sora = Sora({ subsets: ["latin"], variable: "--font-brand" });
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
const serif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-source-serif",
});
export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL || (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "http://localhost:3000")),
  title: "VerRes — read your paper like Reviewer 2 would",
  openGraph: {
    title: "VerRes — read your paper like Reviewer 2 would",
    description: "Every finding links to its evidence.",
    siteName: "VerRes",
    type: "website",
    images: [{ url: "/brand/og-image.png", width: 1200, height: 630 }],
  },
  icons: { icon: [{ url: "/favicon.ico" }, { url: "/brand/icon-192.png", sizes: "192x192" }, { url: "/brand/icon-512.png", sizes: "512x512" }], apple: "/brand/apple-touch-icon.png" },
  twitter: { card: "summary_large_image", images: ["/brand/og-image.png"], title: "VerRes — read your paper like Reviewer 2 would" },
  description:
    "Every finding links to its evidence.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${serif.variable} ${sora.variable}`}>
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
              <Brand />
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
              Every finding links to its evidence.
            </span>
          </footer>
        </Providers>
      </body>
    </html>
  );
}
