/**
 * Mock API implementation — only loaded when `NEXT_PUBLIC_USE_MOCK_DATA` is set.
 *
 * This module is separate from `lib/api.ts` so that Next.js can tree-shake it entirely
 * from production builds when the mock flag is not set.
 */
import { isMockMode } from "./env";
import type { MockScenarioId, MockScenario, MOCK_SCENARIOS, DEFAULT_MOCK_SCENARIO } from "./mock";
import type { ApiErrorBody, ApiErrorCode, EvaluateRequest, EvaluateResponse, GeocodeResult } from "./types";

import { MOCK_SCENARIOS as MOCK_SCENARIOS_FULL, DEFAULT_MOCK_SCENARIO as DEFAULT_MOCK_SCENARIO_FULL } from "./mock";

function findScenario(id: MockScenarioId): MockScenario {
  return MOCK_SCENARIOS_FULL.find((scenario) => scenario.id === id) ?? MOCK_SCENARIOS_FULL[0];
}

async function delay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    function onAbort() {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

async function playScenario(
  id: MockScenarioId,
  signal?: AbortSignal,
): Promise<{ ok: true; response: EvaluateResponse } | { ok: false; scenario: MockScenario }> {
  const scenario = findScenario(id);
  await delay(scenario.latencyMs, signal);

  if (scenario.sample) {
    return {
      ok: true,
      response: { ...scenario.sample, evaluated_at: new Date().toISOString() },
    };
  }
  return { ok: false, scenario };
}

export async function evaluateMock(
  _request: EvaluateRequest,
  options: {
    signal?: AbortSignal;
    mockScenario?: MockScenarioId;
  } = {},
): Promise<EvaluateResponse> {
  if (!isMockMode()) {
    throw new Error("Mock mode not enabled");
  }
  const played = await playScenario(options.mockScenario ?? DEFAULT_MOCK_SCENARIO_FULL, options.signal);
  if (played.ok) return played.response;
  const { status, body } = played.scenario.failure!;
  const { code, message, hint, retryable } = body.error;
  throw new ApiError(message, status, code, hint, retryable);
}

export async function geocodeMock(
  _query: string,
  _options: { signal?: AbortSignal } = {},
): Promise<GeocodeResult[]> {
  if (!isMockMode()) {
    throw new Error("Mock mode not enabled");
  }
  return [
    {
      label: "Phoenix, Arizona",
      lat: 33.4484,
      lon: -112.074,
      state: "AZ",
      climate_zone: {
        name: "Hot-Dry",
        medium_threshold_c: 36,
        high_threshold_c: 39,
      },
    },
    {
      label: "Miami, Florida",
      lat: 25.7617,
      lon: -80.1918,
      state: "FL",
      climate_zone: {
        name: "Hot-Humid",
        medium_threshold_c: 34,
        high_threshold_c: 37,
      },
    },
    {
      label: "Minneapolis, Minnesota",
      lat: 44.9778,
      lon: -93.265,
      state: "MN",
      climate_zone: {
        name: "Cold / Northern",
        medium_threshold_c: 27,
        high_threshold_c: 30,
      },
    },
    {
      label: "Lower Manhattan, New York",
      lat: 40.7128,
      lon: -74.006,
      state: "NY",
      climate_zone: {
        name: "Mixed-Humid",
        medium_threshold_c: 30,
        high_threshold_c: 33,
      },
    },
  ];
}

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