"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { resolveZone, zoneKeyFromInfo } from "@/lib/climate";
import { geocode } from "@/lib/api";
import type { GeocodeResult, SelectedLocation } from "@/lib/types";

/** Generate a ~500m square AOI ring around a point (closed ring, [lon, lat]). */
function buildAoiRing(lat: number, lon: number): [number, number][] {
  // ~0.005° ≈ 500m at mid-latitudes; good enough for a demo AOI.
  const delta = 0.005;
  return [
    [lon - delta, lat - delta],
    [lon + delta, lat - delta],
    [lon + delta, lat + delta],
    [lon - delta, lat + delta],
    [lon - delta, lat - delta],
  ];
}

/** Format a climate zone for the suggestion item. */
function formatZoneLine(zone: GeocodeResult["climate_zone"]): string {
  return `${zone.name} — LOW < ${zone.medium_threshold_c}°C, MEDIUM ${zone.medium_threshold_c}–${zone.high_threshold_c}°C, HIGH ≥ ${zone.high_threshold_c}°C`;
}

export function SearchLocation({
  value,
  onChange,
  onSelect,
  disabled,
  placeholder = "Search US location…",
}: {
  /** Current input text. */
  value: string;
  /** Called on every keystroke. */
  onChange: (value: string) => void;
  /** Called when a suggestion is chosen. */
  onSelect: (location: SelectedLocation) => void;
  /** Disable the input while an evaluation is running. */
  disabled?: boolean;
  placeholder?: string;
}) {
  const [suggestions, setSuggestions] = useState<GeocodeResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [searchError, setSearchError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Close suggestions on escape, click outside, or selection
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setSuggestions([]);
        inputRef.current?.blur();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  // Debounced search
  const runSearch = useCallback(
    async (query: string) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();

      const controller = new AbortController();
      abortRef.current = controller;

      debounceRef.current = setTimeout(async () => {
        if (query.length < 2) {
          setSuggestions([]);
          setSearchError(null);
          return;
        }

        setIsSearching(true);
        setSearchError(null);

        try {
          const results = await geocode(query, { signal: controller.signal });
          setSuggestions(results);
        } catch (caught) {
          if (caught instanceof DOMException && caught.name === "AbortError") return;
          setSearchError("Could not search for locations right now.");
          setSuggestions([]);
        } finally {
          setIsSearching(false);
          setHighlightedIndex(-1);
        }
      }, 250);
    },
    []
  );

  // Trigger search when input changes
  useEffect(() => {
    runSearch(value);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, [value, runSearch]);

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLInputElement>) => {
      if (!suggestions.length) return;

      switch (event.key) {
        case "ArrowDown":
          event.preventDefault();
          setHighlightedIndex((i) => (i + 1) % suggestions.length);
          break;
        case "ArrowUp":
          event.preventDefault();
          setHighlightedIndex((i) => (i - 1 + suggestions.length) % suggestions.length);
          break;
        case "Enter":
          event.preventDefault();
          if (highlightedIndex >= 0 && suggestions[highlightedIndex]) {
            selectSuggestion(suggestions[highlightedIndex]);
          }
          break;
        case "Tab":
          // Let Tab blur naturally; selection happens on click
          break;
      }
    },
    [suggestions, highlightedIndex]
  );

  const selectSuggestion = useCallback(
    (result: GeocodeResult) => {
      const zoneKey = zoneKeyFromInfo(result.climate_zone);
      resolveZone(zoneKey); // Validate the zone can be resolved
      const location: SelectedLocation = {
        label: result.label,
        lat: result.lat,
        lon: result.lon,
        state: result.state,
        aoi: buildAoiRing(result.lat, result.lon),
      };
      onSelect(location);
      onChange(result.label);
      setSuggestions([]);
      setHighlightedIndex(-1);
      inputRef.current?.blur();
    },
    [onChange, onSelect]
  );

  const handleClick = useCallback(
    (result: GeocodeResult) => {
      selectSuggestion(result);
    },
    [selectSuggestion]
  );

  // Scroll highlighted item into view
  useEffect(() => {
    if (highlightedIndex >= 0 && listRef.current) {
      const item = listRef.current.children[highlightedIndex] as HTMLElement | undefined;
      item?.scrollIntoView({ block: "nearest" });
    }
  }, [highlightedIndex]);

  const isOpen = suggestions.length > 0 || searchError !== null || isSearching;

  return (
    <div className="relative w-full">
      <label className="flex flex-col gap-1.5">
        <span className="text-xs font-medium uppercase tracking-widest text-slate-500">
          Work site
        </span>
        <div className="relative">
          <input
            ref={inputRef}
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onFocus={() => runSearch(value)}
            onBlur={() => {
              // Delay closing so click on suggestion registers
              setTimeout(() => setSuggestions([]), 150);
            }}
            disabled={disabled}
            placeholder={placeholder}
            autoComplete="off"
            aria-autocomplete="list"
            aria-controls="location-suggestions"
            aria-expanded={isOpen}
            className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-slate-100 outline-none focus:border-white/30 disabled:opacity-50 disabled:cursor-not-allowed pr-10"
          />
          {isSearching && (
            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500" aria-hidden>
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                  fill="none"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
            </span>
          )}
        </div>
      </label>

      {isOpen && (
        <ul
          ref={listRef}
          id="location-suggestions"
          role="listbox"
          className="absolute z-20 mt-1.5 w-full max-h-60 overflow-auto rounded-lg border border-white/10 bg-slate-950/95 backdrop-blur-sm shadow-lg ring-1 ring-white/5"
        >
          {isSearching && suggestions.length === 0 && (
            <li className="px-4 py-3 text-center text-sm text-slate-500" role="option" aria-disabled>
              Searching…
            </li>
          )}

          {searchError && (
            <li className="px-4 py-3 text-center text-sm text-risk-high" role="option" aria-disabled>
              {searchError}
            </li>
          )}

          {suggestions.map((result, index) => (
            <li
              key={`${result.lat},${result.lon}`}
              role="option"
              aria-selected={index === highlightedIndex}
              onClick={() => handleClick(result)}
              onMouseEnter={() => setHighlightedIndex(index)}
              className={`px-4 py-2.5 text-sm transition ${
                index === highlightedIndex
                  ? "bg-white/5 text-slate-100"
                  : "text-slate-300 hover:bg-white/5"
              }`}
            >
              <div className="flex items-baseline gap-2">
                <span className="font-medium text-slate-100">{result.label}</span>
                {result.state && (
                  <span className="font-mono text-xs text-slate-500 uppercase">
                    {result.state}
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-slate-500">
                {formatZoneLine(result.climate_zone)}
              </p>
            </li>
          ))}

          {suggestions.length === 0 && !isSearching && !searchError && value.length >= 2 && (
            <li className="px-4 py-3 text-center text-sm text-slate-500" role="option" aria-disabled>
              No US matches for "{value}". Try a city name, ZIP code, or landmark.
            </li>
          )}
        </ul>
      )}

      {/* Quick hint when no input yet */}
      {!value && !isOpen && !disabled && (
        <p className="mt-1.5 text-xs text-slate-500">
          Type a city, address, or landmark in the US. Each result shows its climate
          zone and the temperature thresholds that will apply.
        </p>
      )}
    </div>
  );
}