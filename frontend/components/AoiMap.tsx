import { NEUTRAL_FILL, RISK_STYLES } from "@/lib/risk";
import type { Coordinate, RiskLevel } from "@/lib/types";

/**
 * Zero-dependency AOI preview: the polygon ring normalized into a square viewBox, tinted
 * by the current risk level.
 *
 * TODO(map): swap for a real basemap + per-cell heat overlay (MapLibre GL or Leaflet) once
 * the FortyGuard grid geometry is confirmed. This keeps the dashboard demoable meanwhile.
 */
export function AoiMap({
  ring,
  riskLevel,
  label,
}: {
  ring: Coordinate[];
  riskLevel: RiskLevel | null;
  label: string;
}) {
  const fill = riskLevel ? RISK_STYLES[riskLevel].fill : NEUTRAL_FILL;
  const points = normalizeRing(ring);

  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-6">
      <h2 className="text-xs font-medium uppercase tracking-widest text-slate-500">
        Area of interest
      </h2>
      <p className="mt-1.5 text-sm text-slate-300">{label}</p>

      <svg
        viewBox="0 0 100 100"
        className="mt-4 aspect-square w-full rounded-lg bg-slate-900/70"
        role="img"
        aria-label={`AOI outline, ${ring.length - 1} vertices`}
      >
        <defs>
          <pattern id="aoi-grid" width="10" height="10" patternUnits="userSpaceOnUse">
            <path
              d="M 10 0 L 0 0 0 10"
              fill="none"
              stroke="currentColor"
              strokeWidth="0.3"
              className="text-white/10"
            />
          </pattern>
        </defs>
        <rect width="100" height="100" fill="url(#aoi-grid)" />
        <polygon
          points={points}
          fill={fill}
          fillOpacity={0.22}
          stroke={fill}
          strokeWidth={1.2}
          strokeLinejoin="round"
        />
      </svg>

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

/** Fit the ring to a 0–100 viewBox with padding, flipping latitude for screen coords. */
function normalizeRing(ring: Coordinate[]): string {
  const longitudes = ring.map(([lon]) => lon);
  const latitudes = ring.map(([, lat]) => lat);
  const minLon = Math.min(...longitudes);
  const minLat = Math.min(...latitudes);
  const spanLon = Math.max(...longitudes) - minLon || 1e-9;
  const spanLat = Math.max(...latitudes) - minLat || 1e-9;

  const padding = 12;
  const scale = 100 - padding * 2;

  return ring
    .map(([lon, lat]) => {
      const x = padding + ((lon - minLon) / spanLon) * scale;
      const y = padding + (1 - (lat - minLat) / spanLat) * scale;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}
