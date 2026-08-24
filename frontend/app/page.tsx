"use client";

import { useState } from "react";

import { AoiMap } from "@/components/AoiMap";
import { DecisionCard } from "@/components/DecisionCard";
import { HistoryList } from "@/components/HistoryList";
import { ApiError, evaluate } from "@/lib/api";
import { DEMO_AOI, DEMO_AOI_LABEL, DEMO_DATE_TIME } from "@/lib/demo";
import type { EvaluateResponse } from "@/lib/types";

/** What the alert box needs. The backend owns the wording; this only decides layout. */
interface DisplayError {
  message: string;
  hint: string;
  retryable: boolean;
}

export default function DashboardPage() {
  const [dateTime, setDateTime] = useState(DEMO_DATE_TIME);
  const [result, setResult] = useState<EvaluateResponse | null>(null);
  const [history, setHistory] = useState<EvaluateResponse[]>([]);
  const [error, setError] = useState<DisplayError | null>(null);
  const [isEvaluating, setIsEvaluating] = useState(false);

  /** On demand only — no polling timer, so development does not burn API credits. */
  async function runEvaluation() {
    setIsEvaluating(true);
    setError(null);

    try {
      // `datetime-local` yields a naive local timestamp, which is what a site
      // supervisor means by "the shift starts at 13:00".
      const next = await evaluate({ polygon_aoi: DEMO_AOI, date_time: dateTime });
      setResult(next);
      setHistory((previous) => [next, ...previous]);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? { message: caught.message, hint: caught.hint, retryable: caught.retryable }
          : {
              message: "Unexpected error running the agent.",
              hint: "",
              retryable: true,
            },
      );
    } finally {
      setIsEvaluating(false);
    }
  }

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
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-100 outline-none focus:border-white/30"
            />
          </label>

          <button
            type="button"
            onClick={runEvaluation}
            disabled={isEvaluating}
            className="rounded-lg bg-slate-100 px-4 py-2 text-sm font-medium text-slate-900 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isEvaluating ? "Evaluating…" : "Evaluate site"}
          </button>
        </div>
      </header>

      {error && (
        <div
          role="alert"
          className="mt-8 rounded-lg border border-risk-high/40 bg-risk-high/10 px-4 py-3 text-sm text-risk-high"
        >
          <p>{error.message}</p>
          {/* The hint is for whoever is running the demo, not the site supervisor, so it
              sits below the message in a quieter weight. */}
          {error.hint && <p className="mt-1.5 text-xs text-risk-high/70">{error.hint}</p>}
          {error.retryable && (
            <button
              type="button"
              onClick={runEvaluation}
              disabled={isEvaluating}
              className="mt-3 rounded-md border border-risk-high/40 px-3 py-1.5 text-xs font-medium transition hover:bg-risk-high/10 disabled:opacity-50"
            >
              {isEvaluating ? "Retrying…" : "Try again"}
            </button>
          )}
        </div>
      )}

      <div className="mt-8 grid gap-6 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-6">
          {result ? (
            <DecisionCard result={result} />
          ) : (
            <section className="rounded-xl border border-dashed border-white/15 p-10 text-center">
              <p className="text-sm text-slate-400">
                No decision yet. Run an evaluation for{" "}
                <span className="text-slate-200">{DEMO_AOI_LABEL}</span>.
              </p>
            </section>
          )}
          <HistoryList items={history} />
        </div>

        <AoiMap
          ring={DEMO_AOI}
          riskLevel={result?.risk_level ?? null}
          label={DEMO_AOI_LABEL}
        />
      </div>
    </main>
  );
}
