import { DECISION_HEADLINE, RISK_STYLES, formatTemperature, formatTimestamp } from "@/lib/risk";
import type { EvaluateResponse } from "@/lib/types";

/** The current decision, its numbers, and the agent's plain-language output. */
export function DecisionCard({ result }: { result: EvaluateResponse }) {
  const style = RISK_STYLES[result.risk_level];

  return (
    <section
      className={`rounded-xl border ${style.border} ${style.surface} p-6`}
      aria-live="polite"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className={`size-2.5 rounded-full ${style.dot}`} aria-hidden />
            <span className="text-xs font-medium uppercase tracking-widest text-slate-400">
              {result.risk_level} heat risk
            </span>
          </div>
          <h2 className={`mt-2 text-3xl font-semibold tracking-tight ${style.text}`}>
            {result.decision}
          </h2>
          <p className="mt-1 text-sm text-slate-400">{DECISION_HEADLINE[result.decision]}</p>
        </div>

        <dl className="flex gap-8">
          <div>
            <dt className="text-xs uppercase tracking-widest text-slate-500">Peak</dt>
            <dd className="mt-1 font-mono text-2xl text-slate-100">
              {formatTemperature(result.peak_temperature)}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-widest text-slate-500">Average</dt>
            <dd className="mt-1 font-mono text-2xl text-slate-100">
              {formatTemperature(result.average_temperature)}
            </dd>
          </div>
        </dl>
      </div>

      <div className="mt-6 space-y-4 border-t border-white/10 pt-5">
        <div>
          <h3 className="text-xs font-medium uppercase tracking-widest text-slate-500">
            Recommendation
          </h3>
          <p className="mt-1.5 text-slate-100">{result.recommendation}</p>
        </div>
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
    </section>
  );
}
