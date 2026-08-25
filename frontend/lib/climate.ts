/**
 * Climate zone thresholds — the frontend mirror of `backend/app/climate.py`.
 *
 * This is the single source of truth for zone names, thresholds, and display
 * helpers on the client. The backend resolves the zone; the frontend only
 * consumes what the API returns. Never recompute zones from coordinates here.
 *
 * Keep in exact sync with the Python module. If a threshold changes, change it
 * in both places.
 */

export type ZoneKey = "hot-humid" | "hot-dry" | "mixed-humid" | "cold-northern";

export interface ClimateZoneThresholds {
  /** Display name (e.g. "Hot-Humid", "Cold / Northern"). */
  name: string;
  /** LOW/MEDIUM boundary — peak °C at or above this is at least MEDIUM. */
  mediumThresholdC: number;
  /** MEDIUM/HIGH boundary — peak °C at or above this is HIGH. */
  highThresholdC: number;
}

/**
 * The four US climate zones with their peak-temperature thresholds (°C).
 *
 * Band logic (identical to `backend/app/risk.py`):
 *   LOW     = peak < mediumThresholdC
 *   MEDIUM  = mediumThresholdC <= peak < highThresholdC
 *   HIGH    = peak >= highThresholdC
 */
export const ZONE_THRESHOLDS: Record<ZoneKey, ClimateZoneThresholds> = {
  "hot-humid": {
    name: "Hot-Humid",
    mediumThresholdC: 34,
    highThresholdC: 37,
  },
  "hot-dry": {
    name: "Hot-Dry",
    mediumThresholdC: 36,
    highThresholdC: 39,
  },
  "mixed-humid": {
    name: "Mixed-Humid",
    mediumThresholdC: 30,
    highThresholdC: 33,
  },
  "cold-northern": {
    name: "Cold / Northern",
    mediumThresholdC: 27,
    highThresholdC: 30,
  },
};

/** The national default zone key — matches `backend/app/climate.py:DEFAULT_ZONE`. */
export const DEFAULT_ZONE_KEY: ZoneKey = "mixed-humid";

/** Default zone object for convenience. */
export const DEFAULT_ZONE: ClimateZoneThresholds = ZONE_THRESHOLDS[DEFAULT_ZONE_KEY];

/**
 * Resolve a zone key to its thresholds. Falls back to the default zone for any
 * unknown key — mirrors `backend/app/climate.py:resolve_zone()`.
 */
export function resolveZone(key: string | null | undefined): ClimateZoneThresholds {
  if (!key) return DEFAULT_ZONE;
  const normalized = key.toLowerCase().trim() as ZoneKey;
  return ZONE_THRESHOLDS[normalized] ?? DEFAULT_ZONE;
}

/**
 * Given a peak temperature and a zone, return the risk band.
 * Mirrors `backend/app/risk.py:classify()` logic.
 */
export function classifyRisk(
  peakCelsius: number | null,
  zone: ClimateZoneThresholds
): "LOW" | "MEDIUM" | "HIGH" {
  if (peakCelsius === null) return "MEDIUM"; // fail-safe floor, matches backend
  if (peakCelsius >= zone.highThresholdC) return "HIGH";
  if (peakCelsius >= zone.mediumThresholdC) return "MEDIUM";
  return "LOW";
}

/**
 * Format a zone's threshold band for display, e.g. "34–37°C" or "≥ 37°C".
 * Used for the legend in AoiMap and the threshold line in DecisionCard.
 */
export function formatZoneBand(
  zone: ClimateZoneThresholds,
  level: "LOW" | "MEDIUM" | "HIGH"
): string {
  const { mediumThresholdC, highThresholdC } = zone;
  switch (level) {
    case "LOW":
      return `< ${mediumThresholdC}°C`;
    case "MEDIUM":
      return `${mediumThresholdC}–${highThresholdC}°C`;
    case "HIGH":
      return `≥ ${highThresholdC}°C`;
  }
}

/**
 * All zone keys in display order (default first, then hotter, then colder).
 * Useful for dropdowns or ordered legends.
 */
export const ZONE_KEYS_IN_ORDER: ZoneKey[] = [
  "mixed-humid",
  "hot-humid",
  "hot-dry",
  "cold-northern",
];

/**
 * Get the zone key from a ClimateZoneInfo object returned by the API.
 * The API returns the full object; this extracts the slug for local lookups.
 * Returns the default zone key if info is null/undefined or doesn't match.
 */
export function zoneKeyFromInfo(info: {
  name: string;
  medium_threshold_c: number;
  high_threshold_c: number;
} | null | undefined): ZoneKey {
  if (!info) return DEFAULT_ZONE_KEY;
  // Match by thresholds (more reliable than name which might have whitespace diffs)
  for (const [key, zone] of Object.entries(ZONE_THRESHOLDS)) {
    if (
      zone.mediumThresholdC === info.medium_threshold_c &&
      zone.highThresholdC === info.high_threshold_c
    ) {
      return key as ZoneKey;
    }
  }
  return DEFAULT_ZONE_KEY;
}