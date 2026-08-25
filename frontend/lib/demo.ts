import type { Coordinate } from "./types";

/**
 * The demo location, taken from the validated n8n prototype's `HTTP Request` node
 * (`n8n/heatguard-workflow.json`) — lower Manhattan. This exact AOI and work window is the
 * combination already known to return data from FortyGuard, which is what makes it safe to
 * demo live (CLAUDE.md → Demo scenario).
 *
 * Closed ring, `[lon, lat]`, first vertex repeated last.
 */
export const DEMO_AOI: Coordinate[] = [
  [-74.017, 40.705],
  [-74.003, 40.705],
  [-74.003, 40.718],
  [-74.017, 40.718],
  [-74.017, 40.705],
];

export const DEMO_AOI_LABEL = "Construction site — Lower Manhattan, NYC";

/**
 * Generate a ~500m square AOI ring around a point (closed ring, [lon, lat]).
 * ~0.005° ≈ 500m at mid-latitudes; good enough for a demo AOI.
 */
export function buildAoiRing(lat: number, lon: number): Coordinate[] {
  const delta = 0.005;
  return [
    [lon - delta, lat - delta],
    [lon + delta, lat - delta],
    [lon + delta, lat + delta],
    [lon - delta, lat + delta],
    [lon - delta, lat - delta],
  ];
}

/**
 * The default work window: the current local hour, formatted for
 * `<input type="datetime-local">` (`YYYY-MM-DDTHH:mm`, local time, no zone).
 *
 * A function, not a constant — the agent assesses live temperature for the shift you are about
 * to run, so the default is always "now", never a baked-in date. Call it on the client only
 * (see `page.tsx`): computing "now" during server render and again on hydration yields two
 * different strings and trips a React hydration mismatch, which is exactly why this used to be
 * a fixed 2024 constant. Minutes are zeroed because a shift starts on the hour.
 */
export function currentWorkWindow(now: Date = new Date()): string {
  const local = new Date(now);
  local.setMinutes(0, 0, 0);
  const pad = (value: number) => String(value).padStart(2, "0");
  return (
    `${local.getFullYear()}-${pad(local.getMonth() + 1)}-${pad(local.getDate())}` +
    `T${pad(local.getHours())}:${pad(local.getMinutes())}`
  );
}
