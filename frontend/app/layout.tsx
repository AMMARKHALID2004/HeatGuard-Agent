import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "HeatGuard Agent",
  description:
    "Autonomous heat-risk agent for outdoor work: FortyGuard hyperlocal temperature data, " +
    "fixed risk thresholds, and a PROCEED / MODIFY / RESCHEDULE call per shift.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
