"use client";

import { useEffect, useState } from "react";

/**
 * What the dashboard shows while an evaluation is in flight.
 *
 * This exists because the wait is genuinely long and genuinely variable: a FortyGuard heatmap
 * is a submit-and-poll job, so `/api/evaluate` can return in two seconds or grind for thirty
 * (`POLL_MAX_ATTEMPTS` × backoff, then the Groq call on top). A greyed-out button over an
 * empty panel gives a supervisor no way to tell "working" from "hung", and the honest answer
 * to that is not a spinner — it is naming the phase and letting the elapsed seconds run.
 *
 * The phases are indicative, not observed. The backend returns one JSON body at the end and
 * streams nothing, so this cannot know which step is actually running. It is driven by
 * elapsed time against the real default timings, and says so rather than implying telemetry
 * it does not have.
 *
 * Direction 5: Radar sweep on map is the primary loading indicator. This card is secondary,
 * showing phase detail in the briefing panel.
 */

interface Phase {
  /** Seconds elapsed at which this phase starts. */
  at: number;
  label: string;
  detail: string;
}

const PHASES: Phase[] = [
  {
    at: 0,
    label: "Requesting heatmap",
    detail: "Sending the site area and shift time to FortyGuard.",
  },
  {
    at: 3,
    label: "Waiting for heatmap",
    detail: "FortyGuard processes asynchronously; the backend polls until ready.",
  },
  {
    at: 12,
    label: "Still waiting",
    detail: "Large areas take longer. The backend times out at POLL_MAX_ATTEMPTS.",
  },
  {
    at: 22,
    label: "Assessing risk",
    detail: "Computing peak/average temperatures and generating the recommendation.",
  },
];

function phaseFor(seconds: number): Phase {
  // Walk backwards to the last phase whose start time has passed.
  return [...PHASES].reverse().find((phase) => seconds >= phase.at) ?? PHASES[0];
}

export function PendingCard({ mock = false }: { mock?: boolean }) {
  const seconds = useElapsedSeconds();
  const phase = phaseFor(seconds);

  return (
    <section
      className="card-base p-5 animate-fade-in-up"
      aria-busy="true"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="relative flex size-2.5" aria-hidden>
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-ember-500/60" />
              <span className="relative inline-flex size-2.5 rounded-full bg-ember-500" />
            </span>
            <span className="section-label text-ember-500">
              {mock ? "Playing sample" : "Evaluating"}
            </span>
          </div>

          <h2 className="mt-2 text-lg font-semibold tracking-tight text-text">
            {phase.label}
          </h2>
          <p className="mt-1 max-w-md body-base text-text-secondary">{phase.detail}</p>
        </div>

        <div className="text-right">
          <div className="caption-text text-text-muted">Elapsed</div>
          {/* Tabular figures so the card does not jitter as the number grows. */}
          <div className="mt-1 font-mono text-xl tabular-nums text-text">
            {seconds}s
          </div>
        </div>
      </div>

      {/* Skeleton standing in for the decision card's own blocks, so the layout does not
          jump when the real content lands. */}
      <div className="mt-5 space-y-3 border-t border-border pt-4" aria-hidden>
        <div className="h-3 w-20 animate-pulse rounded bg-surface-hover/70" />
        <div className="h-4 w-full animate-pulse rounded bg-surface-hover/50" />
        <div className="h-4 w-3/4 animate-pulse rounded bg-surface-hover/50" />
        <div className="h-3 w-16 animate-pulse rounded bg-surface-hover/70" />
        <div className="h-4 w-1/2 animate-pulse rounded bg-surface-hover/50" />
      </div>

      {seconds >= 25 && (
        <p className="mt-4 caption-text text-text-muted">
          Taking longer than usual. The backend bounds this itself and will return a timeout
          rather than hanging.
        </p>
      )}
    </section>
  );
}

/** Seconds since mount, ticking once a second. Cleared on unmount so no timer outlives it. */
function useElapsedSeconds(): number {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    // `Date.now()` rather than counting ticks: a backgrounded tab throttles timers, and a
    // counter would then under-report a wait the user genuinely sat through.
    const startedAt = Date.now();
    const timer = setInterval(() => {
      setSeconds(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  return seconds;
}