import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * Make `NEXT_PUBLIC_USE_MOCK_DATA` readable from the browser.
   *
   * The dashboard is a client component, and Next only inlines `NEXT_PUBLIC_*` variables into
   * the client bundle automatically. This is the standard Next.js convention for client-accessible
   * environment variables.
   *
   * Safe because it is a UI toggle, not a secret. Nothing else may be added to this block:
   * `env` inlines values into JavaScript that ships to the browser, so putting
   * FORTYGUARD_API_KEY, GROQ_API_KEY or SLACK_WEBHOOK_URL here would publish them
   * (CLAUDE.md → Known issues #5). Those belong in backend/.env, which this app never reads.
   */
  env: {
    NEXT_PUBLIC_USE_MOCK_DATA: process.env.NEXT_PUBLIC_USE_MOCK_DATA ?? "",
  },
};

export default nextConfig;
