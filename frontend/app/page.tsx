"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AoiMap } from "@/components/AoiMap";
import { DecisionCard } from "@/components/DecisionCard";
import { ErrorAlert } from "@/components/ErrorAlert";
import { HistoryList } from "@/components/HistoryList";
import { MockBanner } from "@/components/MockBanner";
import { PendingCard } from "@/components/PendingCard";
import { SearchLocation } from "@/components/SearchLocation";
import { ApiError, evaluate } from "@/lib/api";
import { buildAoiRing, currentWorkWindow } from "@/lib/demo";
import { DEFAULT_MOCK_SCENARIO, type MockScenarioId, isMockMode } from "@/lib/mock";
import type { EvaluateResponse, SelectedLocation } from "@/lib/types";

/**
 * One past evaluation. The backend response carries no id of its own, and `evaluated_at`
 * is only unique to the millisecond, so the key is minted here rather than derived.
 */
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

export default function DashboardPage() {
  // Empty until the client fills it, so server and client first render identically. `now`
  // is only knowable in the browser; see `currentWorkWindow`.
  const [dateTime, setDateTime] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<DisplayError | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [mockScenario, setMockScenario] = useState<MockScenarioId>(DEFAULT_MOCK_SCENARIO);

  // Currently selected location (defaults to demo location)
  const [selectedLocation, setSelectedLocation] = useState<SelectedLocation>(DEMO_LOCATION);
  // Search input text (separate from selectedLocation.label so typing doesn't overwrite the pick)
  const [searchText, setSearchText] = useState(DEMO_LOCATION.label);

  // Read once into state rather than calling `isMockMode()` during render. The value is
  // inlined at build time so it is identical on both sides, but keeping the read in an
  // effect-free constant makes it obvious this is a build flag, not a runtime toggle.
  const [mockMode] = useState(isMockMode);

  const nextId = useRef(1);
  const inFlight = useRef<AbortController | null>(null);

  // Abort whatever is running if this page goes away, so a resolved fetch cannot call
  // `setState` on an unmounted component — and, in mock mode, so a pending timer is cleared.
  useEffect(() => () => inFlight.current?.abort(), []);

  // Default the work window to the current local hour, once, on the client. Kept out of the
  // `useState` initializer on purpose: computing "now" on the server too would render a
  // different string than the browser and trip a hydration mismatch.
  useEffect(() => setDateTime((current) => current || currentWorkWindow()), []);

  const runEvaluation = useCallback(async () => {
    // A second click supersedes the first rather than racing it: without this, two responses
    // can land out of order and the older one wins, leaving a decision on screen that does
    // not match the button press that produced it.
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;

    setIsEvaluating(true);
    setError(null);

    try {
      // `datetime-local` yields a naive local timestamp, which is what a site
      // supervisor means by "the shift starts at 13:00".
      // Include the state code so the backend resolves the same zone the picker previewed.
      const result = await evaluate(
        {
          polygon_aoi: selectedLocation.aoi,
          date_time: dateTime,
          state: selectedLocation.state,
        },
        { signal: controller.signal, mockScenario },
      );
      const entry = { id: nextId.current++, result, location: selectedLocation };
      setHistory((previous) => [entry, ...previous]);
      setSelectedId(entry.id);
    } catch (caught) {
      // The evaluation was superseded or the page unmounted. Not a failure, and showing an
      // error for it would be wrong — the newer request owns the UI now.
      if (caught instanceof DOMException && caught.name === "AbortError") return;
      setError(caught instanceof ApiError ? caught : UNEXPECTED);
    } finally {
      // Only the request that still owns the slot may clear the pending state; a superseded
      // one must not, or the spinner disappears while its replacement is still running.
      if (inFlight.current === controller) {
        inFlight.current = null;
        setIsEvaluating(false);
      }
    }
  }, [dateTime, mockScenario, selectedLocation]);

  const handleLocationSelect = useCallback((location: SelectedLocation) => {
    setSelectedLocation(location);
    setSearchText(location.label);
  }, []);

  const handleSearchChange = useCallback((value: string) => {
    setSearchText(value);
  }, []);

  const selected = history.find((entry) => entry.id === selectedId) ?? null;
  const isViewingPast = selected !== null && history[0]?.id !== selected.id;

  return (
    <main className="mx-auto max-w-6xl px-6 py-12">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">HeatGuard Agent</h1>
          <p className="mt-1 max-w-xl text-sm text-slate-400">
            Hyperlocal heat risk for outdoor work. The agent reads FortyGuard temperature
            data for the site, applies fixed risk thresholds, and calls the shift.
          </p>
        </div>

        <div className="flex flex-col lg:flex-row lg:items-end gap-3 w-full lg:w-auto">
          <div className="w-full lg:w-80">
            <SearchLocation
              value={searchText}
              onChange={handleSearchChange}
              onSelect={handleLocationSelect}
              disabled={isEvaluating}
              placeholder="Search US location…"
            />
          </div>

          <div className="flex flex-col lg:flex-row lg:items-end gap-3 w-full lg:w-auto">
            <label className="flex flex-col gap-1.5 lg:w-48">
              <span className="text-xs font-medium uppercase tracking-widest text-slate-500">
                Shift start
              </span>
              <input
                type="datetime-local"
                value={dateTime}
                onChange={(event) => setDateTime(event.target.value)}
                disabled={isEvaluating}
                className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 outline-none focus:border-white/30 disabled:opacity-50"
                aria-describedby="shift-start-hint"
              />
              <span id="shift-start-hint" className="text-[11px] text-slate-500">
                Local time. The agent reads live temperature for this hour.
              </span>
            </label>

            <button
              type="button"
              onClick={runEvaluation}
              disabled={isEvaluating || !dateTime}
              className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-900 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50 w-full lg:w-auto"
            >
              {isEvaluating ? "Evaluating…" : "Evaluate heat risk"}
            </button>
          </div>
        </div>
      </header>

      {mockMode && (
        <div className="mt-8">
          <MockBanner
            selected={mockScenario}
            onSelect={setMockScenario}
            disabled={isEvaluating}
          />
        </div>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-6">
          {/* Order matters: an error replaces the pending state but never the last good
              decision, so a failed retry does not wipe the card the supervisor was reading. */}
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
              <section className="rounded-xl border border-dashed border-white/15 p-10 text-center">
                <p className="text-sm text-slate-400">
                  No decision yet. Pick a site and a shift start, then press{" "}
                  <span className="font-medium text-slate-200">Evaluate heat risk</span>.
                </p>
              </section>
            )
          )}

          <HistoryList
            items={history.map((e) => ({ id: e.id, result: e.result, location: e.location }))}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </div>

        <AoiMap
          ring={selected?.location.aoi ?? selectedLocation.aoi}
          riskLevel={selected?.result.risk_level ?? null}
          label={selected?.location.label ?? selectedLocation.label}
          isPending={isEvaluating}
          climateZone={selected?.result.climate_zone ?? null}
        />
      </div>
    </main>
  );
}