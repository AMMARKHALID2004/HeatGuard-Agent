"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AoiMap } from "@/components/AoiMap";
import { DecisionCard } from "@/components/DecisionCard";
import { ErrorAlert } from "@/components/ErrorAlert";
import { HistoryList } from "@/components/HistoryList";
import { MockBanner } from "@/components/MockBanner";
import { PendingCard } from "@/components/PendingCard";
import { SearchLocation } from "@/components/SearchLocation";
import { ApiError, evaluate } from "@/lib/api";
import { buildAoiRing } from "@/lib/demo";
import { dateTimeLocalStringInTimezone, formatInTimezone, getTimezone } from "@/lib/timezone";
import { isMockMode } from "@/lib/env";
import type { EvaluateResponse, SelectedLocation } from "@/lib/types";
import type { MockScenarioId } from "@/lib/mock";

// Default mock scenario — "high" is the default so the demo shows the most dramatic state.
// Importing this constant from lib/mock would pull in the full mock bundle, defeating tree-shaking.
const DEFAULT_MOCK_SCENARIO: MockScenarioId = "high";

/** One past evaluation. The backend response carries no id of its own, and `evaluated_at`
 * is only unique to the millisecond, so the key is minted here rather than derived. */
interface HistoryEntry {
  id: number;
  result: EvaluateResponse;
  /** The location that was evaluated, for display in history. */
  location: SelectedLocation;
}

/** What the alert box needs. The backend owns the wording; this only decides layout. */
type DisplayError = Pick<ApiError, "message" | "hint" | "retryable" | "code" | "status">;

const UNEXPECTED: DisplayError = {
  message: "Something went wrong in the dashboard while running the agent.",
  hint: "This is a frontend bug rather than a backend failure — check the browser console.",
  retryable: true,
  code: "unknown",
  status: 0,
};

/** Default demo location (Lower Manhattan) as a SelectedLocation. */
const DEMO_LOCATION: SelectedLocation = {
  label: "Construction site — Lower Manhattan, NYC",
  lat: 40.7115,
  lon: -74.01,
  state: "NY",
  aoi: [
    [-74.017, 40.705],
    [-74.003, 40.705],
    [-74.003, 40.718],
    [-74.017, 40.718],
    [-74.017, 40.705],
  ],
};

/** Time window options — up to 12h ahead matching FortyGuard's forecast window. */
const TIME_WINDOWS = [
  { label: "Now", hours: 0 },
  { label: "+3h", hours: 3 },
  { label: "+6h", hours: 6 },
  { label: "+12h", hours: 12 },
] as const;

type TimeWindowLabel = (typeof TIME_WINDOWS)[number]["label"];

const DECISION_HEADLINE: Record<string, string> = {
  PROCEED: "Work can proceed as planned",
  MODIFY: "Proceed with modifications",
  RESCHEDULE: "Reschedule this shift",
};

export default function DashboardPage() {
  // Currently selected location (defaults to demo location)
  const [selectedLocation, setSelectedLocation] = useState<SelectedLocation>(DEMO_LOCATION);
  // Search input text (separate from selectedLocation.label so typing doesn't overwrite the pick)
  const [searchText, setSearchText] = useState(DEMO_LOCATION.label);

  // Site's timezone (resolved from coordinates)
  const siteTimezone = useMemo(
    () => getTimezone(selectedLocation.lat, selectedLocation.lon),
    [selectedLocation.lat, selectedLocation.lon]
  );

  // Time window selection state
  const [selectedTimeWindow, setSelectedTimeWindow] = useState<TimeWindowLabel>("Now");
  // The actual ISO string sent to backend (computed from site timezone + window)
  const [dateTime, setDateTime] = useState("");

  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<DisplayError | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [mockScenario, setMockScenario] = useState<MockScenarioId>(DEFAULT_MOCK_SCENARIO);
  const [briefingOpen, setBriefingOpen] = useState(false);

  // Read once into state rather than calling `isMockMode()` during render.
  const [mockMode] = useState(isMockMode);

  const nextId = useRef(1);
  const inFlight = useRef<AbortController | null>(null);
  const mapContainerRef = useRef<HTMLDivElement | null>(null);

  // Update dateTime when timezone or time window changes
  useEffect(() => {
    const iso = dateTimeLocalStringInTimezone(
      siteTimezone,
      TIME_WINDOWS.find((w) => w.label === selectedTimeWindow)?.hours ?? 0
    );
    setDateTime(iso);
  }, [siteTimezone, selectedTimeWindow]);

  // Abort whatever is running if this page goes away
  useEffect(() => () => inFlight.current?.abort(), []);

  const runEvaluation = useCallback(async () => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;

    setIsEvaluating(true);
    setError(null);
    setBriefingOpen(false);

    try {
      const result = await evaluate(
        {
          polygon_aoi: selectedLocation.aoi,
          date_time: dateTime,
          state: selectedLocation.state,
        },
        { signal: controller.signal, mockScenario }
      );
      const entry = { id: nextId.current++, result, location: selectedLocation };
      setHistory((previous) => [entry, ...previous]);
      setSelectedId(entry.id);
      setBriefingOpen(true);
    } catch (caught) {
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(caught instanceof ApiError ? caught : UNEXPECTED);
    } finally {
      if (inFlight.current === controller) {
        inFlight.current = null;
        setIsEvaluating(false);
      }
    }
  }, [dateTime, mockScenario, selectedLocation]);

  const handleLocationSelect = useCallback((location: SelectedLocation) => {
    setSelectedLocation(location);
    setSearchText(location.label);
    setSelectedId(null);
    setBriefingOpen(false);
  }, []);

  const handleSearchChange = useCallback((value: string) => {
    setSearchText(value);
  }, []);

  const selected = history.find((entry) => entry.id === selectedId) ?? null;
  const isViewingPast = selected !== null && history[0]?.id !== selected.id;

  // Format current time in site's timezone for display
  const nowInSiteTime = useMemo(() => formatInTimezone(new Date(), siteTimezone), [siteTimezone]);

  // Get the timezone abbreviation for display
  const tzAbbr = useMemo(() => {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: siteTimezone,
      timeZoneName: "short",
    }).formatToParts(new Date());
    return parts.find((p) => p.type === "timeZoneName")?.value ?? siteTimezone;
  }, [siteTimezone]);

  // Extract location name for timezone display
  const locationName = useMemo(() => {
    const parts = selectedLocation.label.split("—");
    return parts[1]?.trim() ?? selectedLocation.label;
  }, [selectedLocation.label]);

  return (
    <div className="min-h-screen bg-bg relative">
      <a href="#main" className="skip-link">
        Skip to main content
      </a>

      {/* Top bar — site identity + site time (above map) */}
      <header className="fixed top-0 left-0 right-0 z-40 p-4 sm:p-6 pointer-events-none">
        <div className="mx-auto max-w-[72rem] pointer-events-auto">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div className="animate-fade-in-up">
              <h1 className="font-display text-display-lg font-semibold tracking-tight text-text">
                HeatGuard Agent
              </h1>
              <p className="mt-1 max-w-xl label-text text-text-secondary">
                {selectedLocation.label}
              </p>
            </div>

            <div className="flex items-center gap-4 flex-wrap">
              {/* Site time display */}
              <div className="flex items-center gap-2 px-4 py-2 bg-surface/80 backdrop-blur border border-border rounded-lg animate-fade-in-up" style={{ animationDelay: "50ms" }}>
                <span className="font-mono tabular-nums text-text">{nowInSiteTime}</span>
                <span className="caption-text text-text-muted">— {locationName} time ({tzAbbr})</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Full-screen map canvas — the mission */}
      <section
        ref={mapContainerRef}
        className="map-canvas"
        aria-label="Area of interest map"
        style={{ opacity: isEvaluating ? 0.4 : 1 }}
      >
        <AoiMap
          ring={selected?.location.aoi ?? selectedLocation.aoi}
          riskLevel={selected?.result.risk_level ?? null}
          label={selected?.location.label ?? selectedLocation.label}
          isPending={isEvaluating}
          climateZone={selected?.result.climate_zone ?? null}
        />

        {/* Radar sweep overlay during evaluation */}
        {isEvaluating && (
          <div className="radar-sweep" aria-hidden="true" />
        )}
      </section>

      {/* Decision briefing — bottom sheet on mobile, permanent right sidebar on desktop */}
      <aside
        className={`fixed inset-x-0 bottom-0 z-[100] lg:fixed lg:inset-y-0 lg:right-0 lg:left-auto lg:w-[480px] lg:max-w-full transition-all duration-300 ease-out ${
          briefingOpen || selected || error || isEvaluating
            ? "translate-y-0 opacity-100 pointer-events-auto"
            : "translate-y-full opacity-0 pointer-events-none lg:translate-y-0 lg:opacity-100 lg:pointer-events-auto"
        }`}
        role="dialog"
        aria-live="polite"
        aria-label="Heat risk decision briefing"
      >
        <div className="briefing-panel h-full lg:h-auto lg:rounded-none lg:border-l lg:border-t-0 lg:border-b-0 lg:border-r-0 flex flex-col">
          {/* Handle / header — mobile only */}
          <div className="lg:hidden flex items-center justify-between p-4 border-b border-border">
            <h2 className="section-label">Mission Briefing</h2>
            <button
              type="button"
              onClick={() => setBriefingOpen(false)}
              className="p-2 rounded-lg hover:bg-surface-hover transition-colors text-text-muted"
              aria-label="Close briefing"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-5 lg:p-6 space-y-5">
            {/* Work site search — always accessible in briefing */}
            <SearchLocation
              value={searchText}
              onChange={handleSearchChange}
              onSelect={handleLocationSelect}
              disabled={isEvaluating}
              placeholder="Search US location…"
            />

            {mockMode && (
              <MockBanner
                selected={mockScenario}
                onSelect={setMockScenario}
                disabled={isEvaluating}
              />
            )}

            {error && (
              <ErrorAlert error={error} onRetry={runEvaluation} isRetrying={isEvaluating} />
            )}

            {isEvaluating ? (
              <PendingCard mock={mockMode} />
            ) : selected ? (
              <DecisionCard
                result={selected.result}
                isHistoric={isViewingPast}
                onShowLatest={() => setSelectedId(history[0]?.id ?? null)}
              />
            ) : (
              !error && (
                <section className="card-base p-9 sm:p-12 text-center animate-fade-in-up">
                  <p className="label-text">
                    No decision yet. Pick a site and a shift start, then press{" "}
                    <span className="font-medium text-text">Execute</span>.
                  </p>
                </section>
              )
            )}

            <HistoryList
              items={history.map((e) => ({ id: e.id, result: e.result, location: e.location }))}
              selectedId={selectedId}
              onSelect={(id) => {
                setSelectedId(id);
                setBriefingOpen(true);
              }}
            />
          </div>

          {/* Timeline scrubber — mission time points */}
          <div className="border-t border-border p-4 sm:p-5 lg:p-6">
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="section-label">Shift Start</span>
                <span className="caption-text font-mono text-text-muted">
                  {nowInSiteTime} {tzAbbr}
                </span>
              </div>

              <div className="timeline-track" role="radiogroup" aria-label="Shift start time">
                {TIME_WINDOWS.map(({ label, hours }) => (
                  <button
                    key={label}
                    type="button"
                    role="radio"
                    aria-checked={selectedTimeWindow === label}
                    onClick={() => {
                      setSelectedTimeWindow(label);
                      setBriefingOpen(true);
                    }}
                    disabled={isEvaluating}
                    data-active={selectedTimeWindow === label}
                    className="timeline-marker"
                  >
                    {label}
                  </button>
                ))}
              </div>

              {/* Execute button — guarded, the only ember element on idle screen */}
              <button
                type="button"
                onClick={runEvaluation}
                disabled={isEvaluating || !dateTime}
                className="execute-btn w-full"
              >
                {isEvaluating ? (
                  <>
                    <svg className="animate-spin mr-2 h-4 w-4" viewBox="0 0 24 24" aria-hidden>
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Evaluating…
                  </>
                ) : (
                  "Execute Evaluation"
                )}
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Mobile briefing trigger when closed */}
      {!briefingOpen && !selected && !error && !isEvaluating && (
        <button
          type="button"
          onClick={() => setBriefingOpen(true)}
          className="lg:hidden fixed bottom-5 left-5 right-5 z-20 execute-btn animate-fade-in-up"
        >
          Open Mission Briefing
        </button>
      )}
    </div>
  );
}