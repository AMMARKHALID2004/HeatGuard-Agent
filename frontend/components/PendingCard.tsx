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
    label: "Requesting the heatmap",
    detail: "Submitting the area and work window to FortyGuard.",
  },
  {
    at: 3,
    label: "Waiting on the heatmap job",
    detail: "FortyGuard processes these asynchronously; the backend polls with backoff.",
  },
  {
    at: 12,
    label: "Still polling",
    detail: "Large areas take longer. The backend gives up at POLL_MAX_ATTEMPTS and returns a 504.",
  },
  {
    at: 22,
    label: "Assessing the readings",
    detail: "Peak and average are computed here, then the model writes the recommendation.",
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
      className="rounded-xl border border-white/10 bg-white/[0.03] p-6"
      aria-busy="true"
      // Announced politely: a screen reader user gets the phase change without having focus
      // yanked off the button they just pressed.
      aria-live="polite"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="relative flex size-2.5" aria-hidden>
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-slate-300 opacity-60" />
              <span className="relative inline-flex size-2.5 rounded-full bg-slate-300" />
            </span>
            <span className="text-xs font-medium uppercase tracking-widest text-slate-400">
              {mock ? "Playing sample" : "Evaluating"}
            </span>
          </div>

          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-100">
            {phase.label}
          </h2>
          <p className="mt-1 max-w-md text-sm text-slate-400">{phase.detail}</p>
        </div>

        <div className="text-right">
          <div className="text-xs uppercase tracking-widest text-slate-500">Elapsed</div>
          {/* Tabular figures so the card does not jitter as the number grows. */}
          <div className="mt-1 font-mono text-2xl tabular-nums text-slate-300">
            {seconds}s
          </div>
        </div>
      </div>

      {/* Skeleton standing in for the decision card's own blocks, so the layout does not
          jump when the real content lands. */}
      <div className="mt-6 space-y-3 border-t border-white/10 pt-5" aria-hidden>
        <div className="h-3 w-24 animate-pulse rounded bg-white/10" />
        <div className="h-4 w-full animate-pulse rounded bg-white/[0.07]" />
        <div className="h-4 w-4/5 animate-pulse rounded bg-white/[0.07]" />
        <div className="h-3 w-20 animate-pulse rounded bg-white/10" />
        <div className="h-4 w-2/3 animate-pulse rounded bg-white/[0.07]" />
      </div>

      {seconds >= 25 && (
        <p className="mt-5 text-xs text-slate-500">
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
