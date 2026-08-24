"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useRef } from "react";

import { NEUTRAL_FILL, RISK_STYLES } from "@/lib/risk";
import type { Coordinate, RiskLevel } from "@/lib/types";

/**
 * The Leaflet half of the AOI map, kept in its own module so `AoiMap` can load it with
 * `ssr: false`. Leaflet reaches for `window`/`document` the moment a map is constructed, so
 * it must never execute during server rendering — importing it here rather than in a shared
 * module is what guarantees that.
 *
 * The whole AOI is tinted by the enforced risk level; there is no per-cell heat overlay yet.
 * TODO(map): once the FortyGuard grid geometry in `services/heatmap.py` is confirmed, draw
 * the per-cell temperatures on top. Tinting the single polygon is the honest amount of
 * spatial detail we currently have.
 */
export function MapCanvas({
  ring,
  riskLevel,
}: {
  ring: Coordinate[];
  riskLevel: RiskLevel | null;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<L.Map | null>(null);
  const polygonRef = useRef<L.Polygon | null>(null);

  // Build the map exactly once. Leaflet owns the DOM node after this, so React must not
  // render into it again; every later change goes through the Leaflet handles above.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || mapRef.current) return;

    // Our rings are GeoJSON order [lon, lat]; Leaflet wants [lat, lon].
    const latlngs = ring.map(([lon, lat]) => [lat, lon] as [number, number]);

    const map = L.map(container, {
      // Let the page scroll past the map instead of the map swallowing the wheel.
      scrollWheelZoom: false,
    });
    mapRef.current = map;

    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      // Attribution is required by both providers — it is why the credit sits bottom-right.
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 20,
    }).addTo(map);

    const polygon = L.polygon(latlngs, styleFor(riskLevel)).addTo(map);
    polygonRef.current = polygon;
    map.fitBounds(polygon.getBounds(), { padding: [24, 24] });

    // Tiles render gray when the container is sized after the map is built — which it is,
    // inside a grid column. Recompute once the layout settles and on any later resize.
    const settle = requestAnimationFrame(() => map.invalidateSize());
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(container);

    return () => {
      cancelAnimationFrame(settle);
      observer.disconnect();
      map.remove();
      mapRef.current = null;
      polygonRef.current = null;
    };
    // `ring` is a stable module constant; rebuilding the map on every render would tear down
    // the tiles mid-interaction. Risk re-tinting is handled by the effect below instead.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-tint the AOI in place when the decision changes, without rebuilding the map.
  useEffect(() => {
    polygonRef.current?.setStyle(styleFor(riskLevel));
  }, [riskLevel]);

  return <div ref={containerRef} className="mt-4 h-[420px] w-full rounded-lg" />;
}

/** Outline + fill for the AOI polygon, neutral until the first decision lands. */
function styleFor(riskLevel: RiskLevel | null): L.PathOptions {
  const color = riskLevel ? RISK_STYLES[riskLevel].fill : NEUTRAL_FILL;
  return { color, weight: 2, fillColor: color, fillOpacity: 0.25 };
}
