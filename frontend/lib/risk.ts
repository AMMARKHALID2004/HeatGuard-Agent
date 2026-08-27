import type { Decision, RiskLevel } from "./types";

/**
 * Presentation only — the thresholds themselves are enforced in `backend/app/risk.py`.
 *
 * `fill` is for inline SVG attributes and carries a literal fallback, since Tailwind only
 * emits theme variables that a used utility references.
 */
export const RISK_STYLES: Record<
  RiskLevel,
  { text: string; border: string; surface: string; dot: string; fill: string }
> = {
  LOW: {
    text: "text-risk-low",
    border: "border-risk-low/40",
    surface: "bg-risk-low/10",
    dot: "bg-risk-low",
    fill: "var(--color-risk-low, oklch(0.74 0.15 155))",
  },
  MEDIUM: {
    text: "text-risk-medium",
    border: "border-risk-medium/40",
    surface: "bg-risk-medium/10",
    dot: "bg-risk-medium",
    fill: "var(--color-risk-medium, oklch(0.8 0.15 78))",
  },
  HIGH: {
    text: "text-risk-high",
    border: "border-risk-high/40",
    surface: "bg-risk-high/10",
    dot: "bg-risk-high",
    fill: "var(--color-risk-high, oklch(0.66 0.19 25))",
  },
  UNKNOWN: {
    text: "text-risk-medium",
    border: "border-risk-medium/40",
    surface: "bg-risk-medium/10",
    dot: "bg-risk-medium",
    fill: "var(--color-risk-medium, oklch(0.8 0.15 78))",
  },
};

/** Neutral outline used before the first evaluation. */
export const NEUTRAL_FILL = "oklch(0.55 0.03 250)";

export const DECISION_HEADLINE: Record<Decision, string> = {
  PROCEED: "Work can proceed as planned",
  MODIFY: "Proceed with modifications",
  RESCHEDULE: "Reschedule this shift",
  NO_DATA: "No temperature data available",
};

export function formatTemperature(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)}°C`;
}

export function formatTimestamp(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleString();
}
