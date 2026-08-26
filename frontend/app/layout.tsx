import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Space_Grotesk } from "next/font/google";
import { IBM_Plex_Sans } from "next/font/google";
import { JetBrains_Mono } from "next/font/google";

import "./globals.css";

/* Display font — Space Grotesk Variable for decision badge, page title, major numbers */
const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
  preload: true,
  weight: ["300", "700"],
});

/* UI Sans — IBM Plex Sans for all labels, body copy, recommendation, reasoning */
const ibmPlexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  preload: true,
  weight: ["400", "500", "600"],
});

/* Monospace — JetBrains Mono Variable for temperatures, coordinates, timestamps */
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
  preload: true,
  weight: ["400", "700"],
});

export const metadata: Metadata = {
  title: "HeatGuard Agent",
  description:
    "Autonomous heat-risk agent for outdoor work: FortyGuard hyperlocal temperature data, " +
    "fixed risk thresholds, and a PROCEED / MODIFY / RESCHEDULE call per shift.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${spaceGrotesk.variable} ${ibmPlexSans.variable} ${jetbrainsMono.variable}`}>
      <body>
        <a href="#main" className="skip-link">
          Skip to main content
        </a>
        <main id="main" className="min-h-dvh lg:h-dvh">{children}</main>
      </body>
    </html>
  );
}