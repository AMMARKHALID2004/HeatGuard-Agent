/**
 * Minimal environment flag check — no mock scenarios imported.
 *
 * This is separate from `lib/mock.ts` so that importing it does not pull in the
 * entire mock data bundle. Next.js can then tree-shake the mock module entirely
 * when `NEXT_PUBLIC_USE_MOCK_DATA` is not set (inlined as empty string at build time).
 */
export function isMockMode(): boolean {
  const flag = process.env.NEXT_PUBLIC_USE_MOCK_DATA || "";
  return ["1", "true", "yes", "on"].includes(flag.trim().toLowerCase());
}