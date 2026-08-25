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
    <section
      role="alert"
      className="card-base border-reschedule-border bg-reschedule-surface p-5 animate-fade-in-up"
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="section-label text-reschedule">
          Evaluation failed
        </span>
        {/* The code is the join between this box and the backend log, which records the real
            cause under the same string. A screenshot is then enough to find the log line. */}
        {error.code !== "unknown" && (
          <code className="font-mono caption-text text-reschedule/70">
            {error.status > 0 ? `${error.status} · ` : ""}
            {error.code}
          </code>
        )}
      </div>

      <p className="mt-2 body-base text-text">{error.message}</p>

      {error.hint && (
        <p className="mt-3 border-l-2 border-reschedule-border/30 pl-3 caption-text text-text-muted">
          {error.hint}
        </p>
      )}

      {error.retryable ? (
        <button
          type="button"
          onClick={onRetry}
          disabled={isRetrying}
          className="mt-4 btn-secondary w-full sm:w-auto"
        >
          {isRetrying ? "Retrying…" : "Try again"}
        </button>
      ) : (
        <p className="mt-4 caption-text text-text-muted">
          This requires a server-side fix — retrying will not help.
        </p>
      )}
    </section>
  );
}