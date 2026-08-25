import { isMockMode } from "./env";
import { evaluateMock, geocodeMock } from "./api-mock";
import type {
  ApiErrorBody,
  ApiErrorCode,
  EvaluateRequest,
  EvaluateResponse,
  GeocodeResult,
} from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/**
 * The port `API_URL` actually points at, for use in the "backend is down" hint.
 *
 * Hardcoding 8000 there was wrong whenever `NEXT_PUBLIC_API_URL` named a different port: the
 * dashboard would tell you to start a server on a port it was not going to call.
 */
function apiPort(): string {
  try {
    return new URL(API_URL).port || "8000";
  } catch {
    return "8000";
  }
}

/**
 * A failure from the backend, already carrying a sentence written to be displayed.
 *
 * `message` is never assembled here: the backend owns the wording, so a status this client
 * has not heard of still shows something a supervisor can read. `hint` is for the developer
 * running the demo and is deliberately kept out of the main error line.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: ApiErrorCode | "unreachable" | "unknown",
    readonly hint: string,
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isErrorBody(body: unknown): body is ApiErrorBody {
  if (typeof body !== "object" || body === null) return false;
  const error = (body as { error?: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

/**
 * Read the backend's error contract, degrading in steps.
 *
 * The structured `error` object is the happy path. A bare FastAPI `detail` still yields a
 * readable sentence. A non-JSON body — an upstream proxy timing out before the request ever
 * reaches uvicorn — falls back to the status code.
 */
async function readError(response: Response): Promise<ApiError> {
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return new ApiError(
      `The server returned an unexpected response (HTTP ${response.status}).`,
      response.status,
      "unknown",
      "Check that the backend is running and that nothing is proxying it.",
      response.status >= 500,
    );
  }

  if (isErrorBody(body)) {
    const { code, message, hint, retryable } = body.error;
    return new ApiError(message, response.status, code, hint, retryable);
  }

  const detail = (body as { detail?: unknown }).detail;
  return new ApiError(
    typeof detail === "string" ? detail : `Request failed with HTTP ${response.status}.`,
    response.status,
    "unknown",
    "",
    response.status >= 500,
  );
}

/**
 * Trigger one agent evaluation. Called on button click only, never on a timer, so
 * development does not burn FortyGuard credits.
 *
 * Throws `ApiError` for every failure, including the network being down, so callers have
 * one type to catch and one `message` to render.
 *
 * With `NEXT_PUBLIC_USE_MOCK_DATA` set this answers from `lib/api-mock.ts` and never touches
 * the network. The mock module is a separate file so Next.js can tree-shake it entirely
 * from production builds when the flag is not set.
 */
export async function evaluate(
  request: EvaluateRequest,
  options: {
    signal?: AbortSignal;
    /** Which sample to play. Ignored unless `NEXT_PUBLIC_USE_MOCK_DATA` is on. */
    mockScenario?: "low" | "medium" | "high" | "no-readings" | "fortyguard-timeout" | "agent-rate-limited" | "not-configured";
  } = {},
): Promise<EvaluateResponse> {
  if (isMockMode()) {
    return evaluateMock(request, options);
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      cache: "no-store",
      signal: options.signal,
    });
  } catch (cause) {
    // An aborted request is the caller's own doing — let it through untranslated so a
    // cancelled evaluation is not reported to the user as a backend failure.
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(
      `Could not reach the backend at ${API_URL}.`,
      0,
      "unreachable",
      `Start it with \`uvicorn app.main:app --reload --port ${apiPort()}\` from backend/, or set ` +
        "NEXT_PUBLIC_USE_MOCK_DATA=1 in frontend/.env.local to work on the UI offline.",
      true,
    );
  }

  if (!response.ok) {
    throw await readError(response);
  }

  return (await response.json()) as EvaluateResponse;
}

/**
 * Search US locations via the backend's geocode proxy. Each suggestion includes its
 * resolved climate zone so the picker can preview which thresholds will apply.
 *
 * Throws `ApiError` on failure (network down, Nominatim unreachable, etc.) — same
 * error type as `evaluate`, so callers have one `catch` block to handle.
 */
export async function geocode(
  query: string,
  options: { signal?: AbortSignal } = {},
): Promise<GeocodeResult[]> {
  if (isMockMode()) {
    return geocodeMock(query, options);
  }

  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/geocode?q=${encodeURIComponent(query)}`, {
      method: "GET",
      cache: "no-store",
      signal: options.signal,
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(
      `Could not reach the backend at ${API_URL}.`,
      0,
      "unreachable",
      `Start it with \`uvicorn app.main:app --reload --port ${apiPort()}\` from backend/, or set ` +
        "NEXT_PUBLIC_USE_MOCK_DATA=1 in frontend/.env.local to work on the UI offline.",
      true,
    );
  }

  if (!response.ok) {
    throw await readError(response);
  }

  return (await response.json()) as GeocodeResult[];
}
