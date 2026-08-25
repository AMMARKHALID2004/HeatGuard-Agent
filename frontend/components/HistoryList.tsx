"use client";

import { DECISION_HEADLINE, formatTemperature, formatTimestamp } from "@/lib/risk";
import type { EvaluateResponse, SelectedLocation } from "@/lib/types";

interface HistoryEntry {
  id: number;
  result: EvaluateResponse;
  location: SelectedLocation;
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
 *
 * Direction 5: Mission log entries — stacked, selected slides half-out (from Sneaker Box Stack challenger).
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
    <section className="animate-fade-in-up">
      <div className="flex items-baseline justify-between gap-4 mb-3">
        <h2 className="section-label">Mission Log</h2>
        {items.length > 0 && (
          <span className="caption-text text-text-muted">
            {items.length} this session
          </span>
        )}
      </div>

      {items.length === 0 ? (
        <p className="caption-text text-text-muted text-center py-4">No evaluations yet this session.</p>
      ) : (
        <ol className="space-y-2" role="list" aria-label="Evaluation history">
          {items.map(({ id, result, location }) => {
            const isSelected = id === selectedId;

            // Map decisions to color keys
            const colorKey = result.decision === "PROCEED" ? "proceed" : result.decision === "MODIFY" ? "modify" : "reschedule";

            return (
              <li key={id}>
                <button
                  type="button"
                  onClick={() => onSelect(id)}
                  aria-current={isSelected ? "true" : undefined}
                  aria-pressed={isSelected}
                  data-selected={isSelected}
                  className="log-entry w-full"
                >
                  <span className={`size-2.5 shrink-0 rounded-full bg-${colorKey}`} aria-hidden />
                  <span className={`font-medium text-${colorKey} flex-1 truncate`}>
                    {result.decision}
                  </span>
                  <span className="caption-text text-text-secondary truncate flex-1 min-w-0">
                    {formatTimestamp(result.evaluated_at)} · {location.label}
                  </span>
                  {/* Only shown when an alert was actually delivered */}
                  {result.alert_sent && (
                    <span className="shrink-0 caption-text text-text-muted" title="Slack alert sent">
                      alerted
                    </span>
                  )}
                  <span className="shrink-0 font-mono text-sm tabular-nums text-text-secondary">
                    {formatTemperature(result.peak_temperature)}
                  </span>
                  {/* Headline read out for accessibility */}
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