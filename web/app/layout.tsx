import type { Metadata } from "next";
import { Inter_Tight, Newsreader, IBM_Plex_Mono } from "next/font/google";
import { Providers } from "@/components/providers";
import "./globals.css";

const mono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400"], preload: false, variable: "--font-plex-mono" });
const inter = Inter_Tight({ subsets: ["latin"], variable: "--font-inter" });
const serif = Newsreader({
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
  icons: { icon: [{ url: "/icon.svg", type: "image/svg+xml" }, { url: "/favicon.ico", sizes: "any" }, { url: "/brand/icon-192.png", sizes: "192x192" }, { url: "/brand/icon-512.png", sizes: "512x512" }], apple: "/brand/apple-touch-icon.png" },
  twitter: { card: "summary_large_image", images: ["/brand/og-image.png"], title: "VerRes — read your paper like Reviewer 2 would" },
  description:
    "Every finding links to its evidence.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${inter.variable} ${serif.variable} ${mono.variable}`}>
      <body className="flex min-h-dvh flex-col font-sans antialiased">
        <Providers>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-white focus:p-3"
          >
            Skip to content
          </a>
          {children}
        </Providers>
      </body>
    </html>
  );
}
