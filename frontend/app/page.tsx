"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AoiMap } from "@/components/AoiMap";
import { DecisionCard } from "@/components/DecisionCard";
import { ErrorAlert } from "@/components/ErrorAlert";
import { HistoryList } from "@/components/HistoryList";
import { MockBanner } from "@/components/MockBanner";
import { PendingCard } from "@/components/PendingCard";
import { ApiError, evaluate } from "@/lib/api";
import { DEMO_AOI, DEMO_AOI_LABEL, currentWorkWindow } from "@/lib/demo";
import { DEFAULT_MOCK_SCENARIO, type MockScenarioId, isMockMode } from "@/lib/mock";
import type { EvaluateResponse } from "@/lib/types";

/**
 * One past evaluation. The backend response carries no id of its own, and `evaluated_at`
 * is only unique to the millisecond, so the key is minted here rather than derived.
 */
interface HistoryEntry {
  id: number;
  result: EvaluateResponse;
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

export default function DashboardPage() {
  // Empty until the client fills it, so server and client first render identically. `now`
  // is only knowable in the browser; see `currentWorkWindow`.
  const [dateTime, setDateTime] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<DisplayError | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [mockScenario, setMockScenario] = useState<MockScenarioId>(DEFAULT_MOCK_SCENARIO);

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
      const result = await evaluate(
        { polygon_aoi: DEMO_AOI, date_time: dateTime },
        { signal: controller.signal, mockScenario },
      );
      const entry = { id: nextId.current++, result };
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
  }, [dateTime, mockScenario]);

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

        <div className="flex items-end gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-xs font-medium uppercase tracking-widest text-slate-500">
              Work window
            </span>
            <input
              type="datetime-local"
              value={dateTime}
              onChange={(event) => setDateTime(event.target.value)}
              disabled={isEvaluating}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 outline-none focus:border-white/30 disabled:opacity-50"
            />
          </label>

          <button
            type="button"
            onClick={runEvaluation}
            disabled={isEvaluating || !dateTime}
            className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-900 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isEvaluating ? "Running…" : "Run Evaluation"}
          </button>
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
                  No decision yet. Run an evaluation for{" "}
                  <span className="text-slate-200">{DEMO_AOI_LABEL}</span>.
                </p>
              </section>
            )
          )}

          <HistoryList
            items={history}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </div>

        <AoiMap
          ring={DEMO_AOI}
          riskLevel={selected?.result.risk_level ?? null}
          label={DEMO_AOI_LABEL}
          isPending={isEvaluating}
        />
      </div>
    </main>
  );
}
