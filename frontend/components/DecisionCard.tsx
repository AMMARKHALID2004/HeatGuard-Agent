"use client";

import { useEffect, useRef, useState } from "react";

import { DECISION_HEADLINE, formatTemperature, formatTimestamp } from "@/lib/risk";
import { resolveZone, zoneKeyFromInfo } from "@/lib/climate";
import type { EvaluateResponse, ClimateZoneInfo } from "@/lib/types";

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
 *
 * Direction 5: Decision hero at full overlay width, variable weight = confidence.
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
  const zoneKey = zoneKeyFromInfo(result.climate_zone);
  const zone = resolveZone(zoneKey);

  // Decision badge weight mapping: LOW=400, MEDIUM=600, HIGH=700, UNKNOWN=600 (confidence)
  const weightMap: Record<string, number> = { LOW: 400, MEDIUM: 600, HIGH: 700, UNKNOWN: 600 };
  const badgeWeight = weightMap[result.risk_level] ?? 600;

  // For split-flap animation: track previous decision
  const prevDecisionRef = useRef<string | null>(null);
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    if (prevDecisionRef.current !== null && prevDecisionRef.current !== result.decision) {
      setAnimate(true);
      // Reset after animation completes
      setTimeout(() => setAnimate(false), 350);
    }
    prevDecisionRef.current = result.decision;
  }, [result.decision]);

  const decisionClass = `decision-hero ${style.decisionClass} ${animate ? "animate-decision-flap" : ""}`;

  return (
    <section className="animate-fade-in-up" aria-live="polite">
      {isHistoric && (
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-1 py-3 bg-surface-hover/40 rounded-t-lg mx-[-1rem] mb-4">
          <span className="caption-text">
            Viewing an earlier evaluation from this session.
          </span>
          {onShowLatest && (
            <button
              type="button"
              onClick={onShowLatest}
              className="label-text font-medium text-text-secondary underline decoration-border underline-offset-2 transition-colors hover:text-text"
            >
              Show latest
            </button>
          )}
        </div>
      )}

      <div className="space-y-5">
        {/* Hero Decision Badge — spans full width, the one thing readable across a room */}
        <div className="w-full">
          <h2
            className={decisionClass}
            data-weight={badgeWeight.toString()}
            style={{ fontWeight: badgeWeight }}
          >
            {result.decision}
          </h2>
          <p className="mt-2 label-text text-text-secondary text-center">{DECISION_HEADLINE[result.decision]}</p>
        </div>

        {/* Climate zone badge + risk level indicator */}
        <div className="flex flex-wrap items-center gap-3 justify-center">
          <div className="flex items-center gap-1.5">
            <span className={`size-2.5 rounded-full ${style.dot}`} aria-hidden />
            <span className="section-label text-text-secondary">{result.risk_level} heat risk</span>
          </div>

          <div className="px-3 py-1 rounded-md bg-modify-surface border border-modify-border text-ember-500 label-text font-medium">
            {zone.name}
          </div>
        </div>

        {/* Temperature readouts — side by side, large mono */}
        <dl className="grid grid-cols-2 gap-4">
          <div className="space-y-1.5 text-center">
            <dt className="section-label">Peak</dt>
            <dd className="temp-display text-text">{formatTemperature(result.peak_temperature)}</dd>
          </div>
          <div className="space-y-1.5 text-center">
            <dt className="section-label">Average</dt>
            <dd className="temp-display text-text-secondary">{formatTemperature(result.average_temperature)}</dd>
          </div>
        </dl>

        {result.peak_temperature === null && (
          <p className="rounded-lg border border-border bg-surface-hover/50 px-4 py-3 caption-text text-text-muted text-center">
            No temperature readings could be retrieved for this area.
            {result.climate_zone && (
              <span className="ml-2 inline-block">
                <br />FortyGuard may not have data for early morning hours. Try a later time window (midday–afternoon) or verify conditions on-site.
              </span>
            )}
          </p>
        )}

        {/* Recommendation + Reasoning */}
        <div className="space-y-5 border-t border-border pt-5">
          {/* Field 5 of 6: what to do about it. The reason a supervisor opened this page. */}
          <div className="space-y-2">
            <h3 className="section-label text-center">Recommendation</h3>
            <p className="body-lg text-center">{result.recommendation}</p>
          </div>

          {/* Field 6 of 6: why. Smaller, because it justifies the call rather than being it. */}
          <div className="space-y-2">
            <h3 className="section-label text-center">Reasoning</h3>
            <p className="body-base text-center">{result.reason}</p>
          </div>
        </div>

        {/* Metadata footer */}
        <div className="flex flex-wrap justify-center gap-x-6 gap-y-1.5 caption-text text-text-muted border-t border-border pt-4">
          <span>Evaluated {formatTimestamp(result.evaluated_at)}</span>
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

/** Presentation styles keyed by risk level — thresholds enforced in backend/app/risk.py */
const RISK_STYLES: Record<
  EvaluateResponse["risk_level"],
  {
    text: string;
    border: string;
    surface: string;
    dot: string;
    decisionClass: string;
  }
> = {
  LOW: {
    text: "text-proceed",
    border: "border-proceed-border",
    surface: "bg-proceed-surface",
    dot: "bg-proceed",
    decisionClass: "decision-proceed",
  },
  MEDIUM: {
    text: "text-modify",
    border: "border-modify-border",
    surface: "bg-modify-surface",
    dot: "bg-modify",
    decisionClass: "decision-modify",
  },
  HIGH: {
    text: "text-reschedule",
    border: "border-reschedule-border",
    surface: "bg-reschedule-surface",
    dot: "bg-reschedule",
    decisionClass: "decision-reschedule",
  },
  UNKNOWN: {
    text: "text-modify",
    border: "border-modify-border",
    surface: "bg-modify-surface",
    dot: "bg-modify",
    decisionClass: "decision-modify",
  },
};