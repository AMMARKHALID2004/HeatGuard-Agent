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
 * Default work window as a `datetime-local` value — also the prototype's validated one.
 * A fixed constant rather than `new Date()` so server and client render identical HTML.
 *
 * NOTE: this is a 2024 date. Re-test with a current date before the demo and update it if
 * FortyGuard returns data for it; `filter_type` may constrain which dates are queryable.
 */
export const DEMO_DATE_TIME = "2024-07-15T14:00";
