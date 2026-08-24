"use client";

import { DECISION_HEADLINE, RISK_STYLES, formatTemperature, formatTimestamp } from "@/lib/risk";
import type { EvaluateResponse } from "@/lib/types";

interface HistoryEntry {
  id: number;
  result: EvaluateResponse;
}

/**
 * Past evaluations from this session, newest first.
 *
 * In memory only, and deliberately so: this is a session log, not a record. Persisting it
 * would mean deciding how long a heat assessment stays valid, and a stale PROCEED restored
 * from localStorage tomorrow morning is exactly the wrong answer to that question.
 *
 * Entries are selectable, which matters during a demo: running three shifts back to back
 * otherwise pushes the interesting decision off screen with no way to get back to it.
 */
export function HistoryList({
  items,
  selectedId,
  onSelect,
}: {
  items: HistoryEntry[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/[0.03] p-6">
      <div className="flex items-baseline justify-between gap-4">
        <h2 className="text-xs font-medium uppercase tracking-widest text-slate-500">
          Evaluation history
        </h2>
        {items.length > 0 && (
          <span className="text-xs text-slate-600">
            {items.length} this session
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No evaluations yet this session.</p>
      ) : (
        <ol className="mt-2 divide-y divide-white/5">
          {items.map(({ id, result }) => {
            const style = RISK_STYLES[result.risk_level];
            const isSelected = id === selectedId;
            return (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => onSelect(id)}
                  aria-current={isSelected ? "true" : undefined}
                  className={`flex w-full items-center justify-between gap-4 rounded-lg px-2 py-2.5 text-left transition ${
                    isSelected ? "bg-white/[0.06]" : "hover:bg-white/[0.03]"
                  }`}
                >
                  <div className="flex min-w-0 items-center gap-2.5">
                    <span className={`size-2 shrink-0 rounded-full ${style.dot}`} aria-hidden />
                    <span className={`text-sm font-medium ${style.text}`}>
                      {result.decision}
                    </span>
                    <span className="truncate text-xs text-slate-500">
                      {formatTimestamp(result.evaluated_at)}
                    </span>
                    {/* Only shown when an alert was actually delivered — the decision card
                        carries the full story, including the failed-to-deliver case. */}
                    {result.alert_sent && (
                      <span className="shrink-0 text-xs text-slate-600" title="Slack alert sent">
                        alerted
                      </span>
                    )}
                  </div>
                  <span className="shrink-0 font-mono text-sm text-slate-400">
                    {formatTemperature(result.peak_temperature)}
                  </span>
                  {/* The decision word alone is ambiguous out of context in a list; the
                      headline is read out to make each row self-describing. */}
                  <span className="sr-only">{DECISION_HEADLINE[result.decision]}</span>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
