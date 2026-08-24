"use client";

import { DECISION_HEADLINE, RISK_STYLES, formatTemperature, formatTimestamp } from "@/lib/risk";
import type { EvaluateResponse } from "@/lib/types";

/**
 * The current decision, its numbers, and the agent's plain-language output.
 *
 * All six fields of the agent contract are labelled and always rendered, including when a
 * temperature is `null`. That last part is the point: the backend returns `null` rather than
 * inventing a number, so "—" under *Peak* is real information — it means the area could not
 * be measured — and a card that hid the row would erase the distinction between "no reading"
 * and "a reading of zero".
 *
 * Colour comes from `risk_level`, never from `decision`. They are locked together by
 * `backend/app/risk.py`, but keying on the risk band keeps this honest about which value is
 * doing the work.
 */
export function DecisionCard({
  result,
  isHistoric = false,
  onShowLatest,
}: {
  result: EvaluateResponse;
  /** True when the user has selected an older entry from the history list. */
  isHistoric?: boolean;
  onShowLatest?: () => void;
}) {
  const style = RISK_STYLES[result.risk_level];

  return (
    <section
      className={`overflow-hidden rounded-xl border ${style.border} ${style.surface}`}
      aria-live="polite"
    >
      {isHistoric && (
        // A past decision looks identical to a current one, which during a demo is a way to
        // read a stale verdict as live. Say so, and offer the way back.
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 bg-slate-950/40 px-6 py-2">
          <span className="text-xs text-slate-400">
            Viewing an earlier evaluation from this session.
          </span>
          {onShowLatest && (
            <button
              type="button"
              onClick={onShowLatest}
              className="text-xs font-medium text-slate-300 underline decoration-slate-600 underline-offset-2 transition hover:text-slate-100"
            >
              Show latest
            </button>
          )}
        </div>
      )}

      <div className="p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            {/* Field 1 of 6: risk level. */}
            <div className="flex items-center gap-2">
              <span className={`size-2.5 rounded-full ${style.dot}`} aria-hidden />
              <span className="text-xs font-medium uppercase tracking-widest text-slate-400">
                {result.risk_level} heat risk
              </span>
            </div>

            {/* Field 2 of 6: the decision itself, the one thing readable across a room. */}
            <h2 className={`mt-2 text-3xl font-semibold tracking-tight ${style.text}`}>
              {result.decision}
            </h2>
            <p className="mt-1 text-sm text-slate-400">{DECISION_HEADLINE[result.decision]}</p>
          </div>

          {/* Fields 3 and 4: the measured temperatures. Tabular figures so the two columns
              line up regardless of value width. */}
          <dl className="flex gap-8">
            <div>
              <dt className="text-xs uppercase tracking-widest text-slate-500">Peak</dt>
              <dd className="mt-1 font-mono text-2xl tabular-nums text-slate-100">
                {formatTemperature(result.peak_temperature)}
              </dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-widest text-slate-500">Average</dt>
              <dd className="mt-1 font-mono text-2xl tabular-nums text-slate-100">
                {formatTemperature(result.average_temperature)}
              </dd>
            </div>
          </dl>
        </div>

        {result.peak_temperature === null && (
          <p className="mt-4 rounded-lg border border-white/10 bg-slate-950/40 px-3 py-2 text-xs text-slate-400">
            No temperature readings were available for this area, so the risk level is a
            fail-safe floor rather than a measurement.
          </p>
        )}

        <div className="mt-6 space-y-4 border-t border-white/10 pt-5">
          {/* Field 5 of 6: what to do about it. The reason a supervisor opened this page. */}
          <div>
            <h3 className="text-xs font-medium uppercase tracking-widest text-slate-500">
              Recommendation
            </h3>
            <p className="mt-1.5 text-slate-100">{result.recommendation}</p>
          </div>
          {/* Field 6 of 6: why. Smaller, because it justifies the call rather than being it. */}
          <div>
            <h3 className="text-xs font-medium uppercase tracking-widest text-slate-500">
              Reasoning
            </h3>
            <p className="mt-1.5 text-sm text-slate-300">{result.reason}</p>
          </div>
        </div>

        <div className="mt-5 flex flex-wrap gap-x-5 gap-y-1 text-xs text-slate-500">
          <span>Evaluated {formatTimestamp(result.evaluated_at)}</span>
          {result.activity_id && <span className="font-mono">job {result.activity_id}</span>}
          <span>
            {result.alert_sent
              ? "Slack alert sent"
              : result.decision === "RESCHEDULE"
                ? "Slack alert not delivered"
                : "No alert needed"}
          </span>
        </div>
      </div>
    </section>
  );
}
