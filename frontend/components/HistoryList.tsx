import { RISK_STYLES, formatTemperature, formatTimestamp } from "@/lib/risk";
import type { EvaluateResponse } from "@/lib/types";

/** Past evaluations from this session, newest first. Kept in memory only. */
export function HistoryList({ items }: { items: EvaluateResponse[] }) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-6">
      <h2 className="text-xs font-medium uppercase tracking-widest text-slate-500">
        Evaluation history
      </h2>

      {items.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">
          No evaluations yet this session.
        </p>
      ) : (
        <ol className="mt-3 divide-y divide-white/5">
          {items.map((item, index) => {
            const style = RISK_STYLES[item.risk_level];
            return (
              <li
                key={`${item.evaluated_at}-${index}`}
                className="flex items-center justify-between gap-4 py-2.5"
              >
                <div className="flex min-w-0 items-center gap-2.5">
                  <span className={`size-2 shrink-0 rounded-full ${style.dot}`} aria-hidden />
                  <span className={`text-sm font-medium ${style.text}`}>{item.decision}</span>
                  <span className="truncate text-xs text-slate-500">
                    {formatTimestamp(item.evaluated_at)}
                  </span>
                </div>
                <span className="shrink-0 font-mono text-sm text-slate-400">
                  {formatTemperature(item.peak_temperature)}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
