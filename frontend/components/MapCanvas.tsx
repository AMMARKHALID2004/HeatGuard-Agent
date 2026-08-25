"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useRef } from "react";

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
 *
 * Direction 5 enhancement: gradient fringe on AOI ring showing spatial variance (from
 * Iridescent Cloud Edge challenger donation).
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
  const gradientRef = useRef<L.Polygon | null>(null);

  // Rebuild the map when the AOI ring changes (new location selected).
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Clean up previous map if exists
    if (mapRef.current) {
      mapRef.current.remove();
      mapRef.current = null;
      polygonRef.current = null;
      gradientRef.current = null;
    }

    // Our rings are GeoJSON order [lon, lat]; Leaflet wants [lat, lon].
    const latlngs = ring.map(([lon, lat]) => [lat, lon] as [number, number]);

    const map = L.map(container, {
      // Let the page scroll past the map instead of the map swallowing the wheel.
      scrollWheelZoom: false,
      attributionControl: false, // We handle attribution in AoiMap
      zoomControl: false,
    });
    mapRef.current = map;

    L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
      // Attribution is required by both providers — it is why the credit sits bottom-right.
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 20,
    }).addTo(map);

    // Add zoom control in bottom-right (out of the way)
    L.control.zoom({ position: "bottomright" }).addTo(map);

    // Main AOI polygon
    const polygon = L.polygon(latlngs, styleFor(riskLevel)).addTo(map);
    polygonRef.current = polygon;

    // Gradient fringe — subtle outer ring with risk-color gradient (Direction 5: Iridescent Cloud Edge)
    if (riskLevel) {
      const colors = getGradientColors(riskLevel);
      const gradientPolygon = L.polygon(latlngs, {
        color: colors.outer,
        weight: 3,
        fillColor: colors.inner,
        fillOpacity: 0.08,
        dashArray: "8, 4",
        interactive: false,
      }).addTo(map);
      gradientRef.current = gradientPolygon;
    }

    map.fitBounds(polygon.getBounds(), { padding: [40, 40] });

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
      gradientRef.current = null;
    };
  }, [ring]);

  // Re-tint the AOI in place when the decision changes, without rebuilding the map.
  useEffect(() => {
    polygonRef.current?.setStyle(styleFor(riskLevel));

    // Update gradient fringe
    if (gradientRef.current && riskLevel) {
      const colors = getGradientColors(riskLevel);
      gradientRef.current.setStyle({
        color: colors.outer,
        fillColor: colors.inner,
      });
    } else if (gradientRef.current) {
      gradientRef.current.remove();
      gradientRef.current = null;
    }
  }, [riskLevel]);

  return <div ref={containerRef} className="h-full w-full" />;
}

/** Outline + fill for the AOI polygon, neutral until the first decision lands. */
function styleFor(riskLevel: RiskLevel | null): L.PathOptions {
  // Map risk levels to CSS variable colors (oklch values from globals.css)
  const colors: Record<RiskLevel, { color: string; fillColor: string }> = {
    LOW: {
      color: "oklch(0.68 0.12 250)",     // proceed blue-gray
      fillColor: "oklch(0.68 0.12 250 / 0.15)",
    },
    MEDIUM: {
      color: "oklch(0.62 0.18 55)",      // ember
      fillColor: "oklch(0.62 0.18 55 / 0.15)",
    },
    HIGH: {
      color: "oklch(0.52 0.22 25)",      // deep crimson
      fillColor: "oklch(0.52 0.22 25 / 0.15)",
    },
  };

  const neutral = {
    color: "oklch(0.55 0.03 250)",
    fillColor: "oklch(0.55 0.03 250 / 0.1)",
  };

  const { color, fillColor } = riskLevel ? colors[riskLevel] : neutral;
  return { color, weight: 2, fillColor, fillOpacity: 1 };
}

/** Gradient fringe colors for the outer ring — spatial variance hint */
function getGradientColors(riskLevel: RiskLevel): { inner: string; outer: string } {
  const gradients: Record<RiskLevel, { inner: string; outer: string }> = {
    LOW: {
      inner: "oklch(0.68 0.12 250 / 0.25)",
      outer: "oklch(0.68 0.12 250)",
    },
    MEDIUM: {
      inner: "oklch(0.62 0.18 55 / 0.25)",
      outer: "oklch(0.62 0.18 55)",
    },
    HIGH: {
      inner: "oklch(0.52 0.22 25 / 0.25)",
      outer: "oklch(0.52 0.22 25)",
    },
  };
  return gradients[riskLevel];
}