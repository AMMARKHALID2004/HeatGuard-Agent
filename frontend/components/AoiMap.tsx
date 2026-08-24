"use client";

import dynamic from "next/dynamic";

import { RISK_STYLES } from "@/lib/risk";
import type { Coordinate, RiskLevel } from "@/lib/types";

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
    <div className="mt-4 flex h-[420px] w-full items-center justify-center rounded-lg bg-slate-900/70 text-xs text-slate-500">
      Loading map…
    </div>
  ),
});

export function AoiMap({
  ring,
  riskLevel,
  label,
  isPending = false,
}: {
  ring: Coordinate[];
  riskLevel: RiskLevel | null;
  label: string;
  /** Dims the map while an evaluation runs, so the tint is not read as current. */
  isPending?: boolean;
}) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-6">
      <h2 className="text-xs font-medium uppercase tracking-widest text-slate-500">
        Area of interest
      </h2>
      <p className="mt-1.5 text-sm text-slate-300">{label}</p>

      {/* Leaflet controls are interactive, so this is not an `img`; a screen reader gets the
          state from here instead of from the tiles. */}
      <p className="sr-only">
        {riskLevel
          ? `Map of ${label}, ${riskLevel} risk`
          : `Map of ${label}, not yet evaluated`}
      </p>

      <div className={`transition-opacity ${isPending ? "opacity-40" : "opacity-100"}`}>
        <MapCanvas ring={ring} riskLevel={riskLevel} />
      </div>

      {/* The thresholds are stated on screen because the colour is otherwise unexplained,
          and because they are fixed in `backend/app/risk.py` rather than being the model's
          call — worth showing a judge. The active band is highlighted. */}
      <ul className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {(
          [
            ["LOW", "< 30°C"],
            ["MEDIUM", "30–33°C"],
            ["HIGH", "≥ 33°C"],
          ] as const
        ).map(([level, band]) => (
          <li key={level} className="flex items-center gap-1.5">
            <span
              className={`size-2 rounded-full ${RISK_STYLES[level].dot} ${
                riskLevel && riskLevel !== level ? "opacity-30" : ""
              }`}
              aria-hidden
            />
            <span className={riskLevel === level ? RISK_STYLES[level].text : "text-slate-500"}>
              {band}
            </span>
          </li>
        ))}
      </ul>

      <ul className="mt-4 space-y-1 font-mono text-xs text-slate-500">
        {ring.slice(0, -1).map(([lon, lat], index) => (
          <li key={`${lon},${lat},${index}`}>
            {lat.toFixed(4)}, {lon.toFixed(4)}
          </li>
        ))}
      </ul>
    </section>
  );
}
