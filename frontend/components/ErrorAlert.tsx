"use client";

import type { ApiError } from "@/lib/api";

/**
 * The failure state, rendered straight from the backend's error contract.
 *
 * Nothing here composes its own wording. `backend/app/errors.py` writes one sentence per
 * failure aimed at whoever is looking at the dashboard, and this displays it — which is what
 * lets a status this frontend has never heard of still produce something readable instead of
 * "Error: 502".
 *
 * The three fields map to three different jobs:
 *   `message`   — for the site supervisor. The largest text in the box.
 *   `hint`      — for whoever is running the demo. Quieter, below, and never shown to the
 *                 supervisor as if it were advice about the weather.
 *   `retryable` — whether pressing the button again could plausibly work. A missing API key
 *                 is not retryable, and offering a retry there would be a lie.
 */
export function ErrorAlert({
  error,
  onRetry,
  isRetrying,
}: {
  error: Pick<ApiError, "message" | "hint" | "retryable" | "code" | "status">;
  onRetry: () => void;
  isRetrying: boolean;
}) {
  return (
    <div
      role="alert"
      className="rounded-xl border border-risk-high/40 bg-risk-high/10 px-5 py-4"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="text-xs font-medium uppercase tracking-widest text-risk-high/80">
          Evaluation failed
        </span>
        {/* The code is the join between this box and the backend log, which records the real
            cause under the same string. A screenshot is then enough to find the log line. */}
        {error.code !== "unknown" && (
          <code className="font-mono text-xs text-risk-high/60">
            {error.status > 0 ? `${error.status} · ` : ""}
            {error.code}
          </code>
        )}
      </div>

      <p className="mt-1.5 text-sm text-slate-100">{error.message}</p>

      {error.hint && (
        <p className="mt-2 border-l-2 border-risk-high/30 pl-3 text-xs leading-relaxed text-slate-400">
          {error.hint}
        </p>
      )}

      {error.retryable ? (
        <button
          type="button"
          onClick={onRetry}
          disabled={isRetrying}
          className="mt-3.5 rounded-md border border-risk-high/40 px-3 py-1.5 text-xs font-medium text-slate-100 transition hover:bg-risk-high/10 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isRetrying ? "Retrying…" : "Try again"}
        </button>
      ) : (
        // No button at all rather than a disabled one: this failure needs someone to change
        // a config value and restart the backend, and a greyed-out "Try again" would suggest
        // waiting is the answer.
        <p className="mt-3.5 text-xs text-slate-500">
          Retrying will not help until this is fixed on the server.
        </p>
      )}
    </div>
  );
}
