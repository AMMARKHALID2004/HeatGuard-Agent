"use client";

import dynamic from "next/dynamic";

import { resolveZone, zoneKeyFromInfo } from "@/lib/climate";
import type { Coordinate, RiskLevel, ClimateZoneInfo } from "@/lib/types";

/**
 * Leaflet must not run on the server (it reaches for `window` when the map is built), so the
 * tile canvas is loaded client-only. The card chrome around it — label, threshold legend and
 * coordinates — renders immediately; only the map waits for the browser.
 *
 * The public shape is unchanged from the SVG placeholder this replaces, so `page.tsx` is
 * untouched. TODO(map) for the per-cell heat overlay now lives in `MapCanvas.tsx`.
 */
const MapCanvas = dynamic(() => import("./MapCanvas").then((m) => m.MapCanvas), {
  ssr: false,
  loading: () => (
    <div className="h-full w-full flex items-center justify-center rounded-lg bg-surface/70 caption-text text-text-muted">
      Loading map…
    </div>
  ),
});

export function AoiMap({
  ring,
  riskLevel,
  label,
  isPending = false,
  climateZone,
}: {
  ring: Coordinate[];
  riskLevel: RiskLevel | null;
  label: string;
  /** Dims the map while an evaluation runs, so the tint is not read as current. */
  isPending?: boolean;
  /** The climate zone resolved for this evaluation, for the threshold legend. */
  climateZone?: ClimateZoneInfo | null;
}) {
  const zoneKey = zoneKeyFromInfo(climateZone ?? null);
  const zone = resolveZone(zoneKey);

  return (
    <div className="h-full w-full relative">
      {/* Map canvas — full screen */}
      <div className="h-full w-full">
        <MapCanvas ring={ring} riskLevel={riskLevel} />
      </div>

      {/* Threshold legend — bottom-left overlay on map */}
      <div className="absolute bottom-5 left-5 right-5 sm:left-5 sm:right-auto sm:max-w-xs pointer-events-none z-10">
        <div className="card-elevated p-3 pointer-events-auto animate-fade-in-up" style={{ animationDelay: "200ms" }}>
          <p className="section-label mb-2">Temperature thresholds</p>
          <ul className="flex flex-col gap-2">
            {(
              [
                ["LOW", `< ${zone.mediumThresholdC}°C`, "proceed"],
                ["MEDIUM", `${zone.mediumThresholdC}–${zone.highThresholdC}°C`, "modify"],
                ["HIGH", `≥ ${zone.highThresholdC}°C`, "reschedule"],
              ] as const
            ).map(([level, band, colorKey]) => (
              <li key={level} className="flex items-center gap-2">
                <span
                  className={`size-2 rounded-full transition-all ${
                    riskLevel && riskLevel !== level ? "opacity-30" : "opacity-100"
                  } bg-${colorKey}`}
                  aria-hidden
                />
                <span className={`caption-text ${
                  riskLevel === level ? `text-${colorKey} font-medium` : "text-text-muted"
                }`}>
                  {band}
                </span>
                {riskLevel === level && (
                  <span className="ml-auto size-1.5 rounded-full bg-${colorKey} animate-pulse" aria-hidden />
                )}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Climate zone — top-right */}
      <div className="absolute top-20 right-5 z-10 pointer-events-none sm:top-[100px]">
        <div className="card-elevated px-3 py-2 pointer-events-auto animate-fade-in-up" style={{ animationDelay: "300ms" }}>
          <p className="caption-text text-text-muted flex items-center gap-2">
            <span className="font-medium text-text">Climate zone:</span>
            <span className="font-medium text-ember-500">{zone.name}</span>
          </p>
        </div>
      </div>

      {/* Coordinates — bottom-right, collapsible */}
      <details className="absolute bottom-5 right-5 z-10 pointer-events-none group">
        <summary className="card-elevated px-3 py-2 pointer-events-auto cursor-pointer select-none flex items-center gap-2 caption-text text-text-muted">
          <span>Coordinates</span>
          <svg className="size-4 transition-transform group-open:rotate-180" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
            <path d="M6 9l6 6 6-6" />
          </svg>
        </summary>
        <div className="card-elevated mt-2 min-w-[180px] pointer-events-auto animate-fade-in-up">
          <ul className="p-3 space-y-1 font-mono text-xs text-text-muted border-t border-border">
            {ring.slice(0, -1).map(([lon, lat], index) => (
              <li key={`${lon},${lat},${index}`} className="tabular-nums flex items-center gap-2">
                <span className="text-text-muted/50">{index + 1}.</span>
                <span>{lat.toFixed(4)}, {lon.toFixed(4)}</span>
              </li>
            ))}
          </ul>
        </div>
      </details>
    </div>
  );
}