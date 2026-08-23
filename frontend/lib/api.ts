import type { EvaluateRequest, EvaluateResponse } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** FastAPI puts the message in `detail`, which is a string or a list of validation objects. */
async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((item) => item?.msg ?? JSON.stringify(item)).join("; ");
    }
  } catch {
    // Non-JSON error body (proxy timeout, backend down) — fall through.
  }
  return `Request failed with HTTP ${response.status}`;
}

/**
 * Trigger one agent evaluation. Called on button click only, never on a timer, so
 * development does not burn FortyGuard credits.
 */
export async function evaluate(request: EvaluateRequest): Promise<EvaluateResponse> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/api/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(`Could not reach the backend at ${API_URL}. Is uvicorn running?`, 0);
  }

  if (!response.ok) {
    throw new ApiError(await readErrorDetail(response), response.status);
  }

  return (await response.json()) as EvaluateResponse;
}
