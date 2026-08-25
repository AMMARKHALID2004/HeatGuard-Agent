/**
 * Sample responses for offline UI work (`USE_MOCK_DATA`).
 *
 * The dashboard's hardest states to reach are the ones you most need to look at: a 504 needs
 * FortyGuard to actually stall, a 503 needs Groq's free tier to actually throttle you, and a
 * heatmap with no readable temperatures needs a payload shape nobody has seen yet. Mock mode
 * makes every one of them a click away, with no API credits spent and no network.
 *
 * Two rules kept these honest:
 *
 * 1. **The failures are copied verbatim from `backend/app/errors.py`.** If the wording here
 *    drifts from the wording there, this stops being useful for UI work — the whole point is
 *    to lay out real sentences at their real length, not lorem ipsum standing in for them.
 * 2. **Mock output announces itself.** Every `activity_id` starts with `mock-`, which the
 *    decision card already renders, and `MockBanner` sits above the dashboard. A sample
 *    PROCEED that reads as a real one is a demo hazard: nobody should be able to mistake
 *    invented data for a measurement, least of all during judging.
 */

import type { ApiErrorBody, ClimateZoneInfo, EvaluateResponse, GeocodeResult } from "./types";

/** A response minus the timestamp, which is stamped when the scenario is played. */
type Sample = Omit<EvaluateResponse, "evaluated_at">;

/**
 * Zone previews for mock mode, mirroring `backend/app/climate.py`. Mock mode never resolves
 * zones itself — it hands back the same shape the real backend would, so the dashboard's
 * zone/threshold display is exercised offline exactly as it is against a live API.
 */
const ZONE_MIXED_HUMID: ClimateZoneInfo = {
  name: "Mixed-Humid",
  medium_threshold_c: 30,
  high_threshold_c: 33,
};
const ZONE_HOT_DRY: ClimateZoneInfo = { name: "Hot-Dry", medium_threshold_c: 36, high_threshold_c: 39 };
const ZONE_HOT_HUMID: ClimateZoneInfo = {
  name: "Hot-Humid",
  medium_threshold_c: 34,
  high_threshold_c: 37,
};
const ZONE_COLD: ClimateZoneInfo = {
  name: "Cold / Northern",
  medium_threshold_c: 27,
  high_threshold_c: 30,
};

export type MockScenarioId =
  | "low"
  | "medium"
  | "high"
  | "no-readings"
  | "fortyguard-timeout"
  | "agent-rate-limited"
  | "not-configured";

export interface MockScenario {
  id: MockScenarioId;
  /** Short label for the scenario picker. */
  label: string;
  /** Grouping for the picker, so decisions and failures do not read as one list. */
  kind: "decision" | "failure";
  /**
   * How long to stall before answering. Deliberately compressed: a real evaluation is a
   * FortyGuard poll plus a Groq call, so 6–12s is normal. Waiting that long on every click
   * would make UI work miserable, so this is just long enough to see the pending state.
   */
  latencyMs: number;
  sample?: Sample;
  failure?: { status: number; body: ApiErrorBody };
}

const LOW: Sample = {
  risk_level: "LOW",
  peak_temperature: 24.6,
  average_temperature: 22.8,
  decision: "PROCEED",
  recommendation:
    "Standard summer precautions are enough. Keep drinking water available at the site " +
    "entrance and check in with the crew at the midday break.",
  reason:
    "Peak temperature of 24.6 °C across the site is below the 30 °C LOW threshold, so no " +
    "heat-specific changes to the shift are warranted.",
  climate_zone: ZONE_MIXED_HUMID,
  activity_id: "mock-low-8c14",
  alert_sent: false,
};

const MEDIUM: Sample = {
  risk_level: "MEDIUM",
  peak_temperature: 31.4,
  average_temperature: 29.7,
  decision: "MODIFY",
  recommendation:
    "Move the concrete pour and any other sustained exertion to before 11:00. Add a shaded " +
    "10-minute break each hour after midday, and pair workers so nobody is on the deck alone.",
  reason:
    "Peak temperature of 31.4 °C falls in the 30–33 °C MEDIUM band. The shift is workable, " +
    "but continuous exertion through the afternoon carries real heat-illness risk.",
  climate_zone: ZONE_MIXED_HUMID,
  activity_id: "mock-med-4b7f",
  alert_sent: false,
};

const HIGH: Sample = {
  risk_level: "HIGH",
  peak_temperature: 41.2,
  average_temperature: 38.4,
  decision: "RESCHEDULE",
  recommendation:
    "Do not run the afternoon shift. Move all outdoor work to a 05:30–10:00 window and keep " +
    "only shaded, low-exertion tasks on site after that. Notify the site supervisor now so " +
    "the crew is not travelling in for nothing.",
  reason:
    "Peak temperature of 41.2 °C is well above the 33 °C HIGH threshold, and the site " +
    "average of 38.4 °C means there is no cooler corner to rotate people through.",
  climate_zone: ZONE_MIXED_HUMID,
  activity_id: "mock-high-1e90",
  alert_sent: true,
};

/**
 * The fail-safe: a heatmap the parser could not read.
 *
 * `null` temperatures with a MEDIUM/MODIFY floor, not a PROCEED — `backend/app/risk.py`
 * refuses to issue a safety claim it has no measurement to back. Worth having here because it
 * is the one state that renders "—" in both temperature slots, and it is easy to lay out a
 * card that quietly assumes those are always numbers.
 */
const NO_READINGS: Sample = {
  risk_level: "MEDIUM",
  peak_temperature: null,
  average_temperature: null,
  decision: "MODIFY",
  recommendation:
    "Treat this as a MEDIUM-risk shift until the temperature data can be re-read. Apply " +
    "hourly shaded breaks and avoid scheduling sustained exertion after midday.",
  reason:
    "No usable temperature readings were found for this area, so risk could not be measured. " +
    "Defaulting to MEDIUM rather than issuing a go-ahead the data cannot support.",
  climate_zone: ZONE_MIXED_HUMID,
  activity_id: "mock-null-77a2",
  alert_sent: false,
};

/** Build a failure body in the exact shape `backend/app/errors.py` returns. */
function failure(
  status: number,
  code: ApiErrorBody["error"]["code"],
  message: string,
  hint: string,
  retryable: boolean,
): { status: number; body: ApiErrorBody } {
  // `detail` duplicates `message` upstream, for clients that only read FastAPI's default
  // field. Mirrored here so mock mode exercises the same parsing path as the real backend.
  return { status, body: { detail: message, error: { code, message, hint, retryable } } };
}

export const MOCK_SCENARIOS: MockScenario[] = [
  { id: "low", label: "LOW · Proceed", kind: "decision", latencyMs: 1100, sample: LOW },
  { id: "medium", label: "MEDIUM · Modify", kind: "decision", latencyMs: 1300, sample: MEDIUM },
  { id: "high", label: "HIGH · Reschedule", kind: "decision", latencyMs: 1500, sample: HIGH },
  {
    id: "no-readings",
    label: "No readings",
    kind: "decision",
    latencyMs: 1200,
    sample: NO_READINGS,
  },
  {
    id: "fortyguard-timeout",
    label: "Timeout (504)",
    kind: "failure",
    // Longer on purpose: this is the failure that arrives after a wait, and the pending state
    // has to hold up for the whole of it.
    latencyMs: 2600,
    failure: failure(
      504,
      "fortyguard_timeout",
      "The temperature service did not finish in time. Nothing is wrong with the request — try again.",
      "FortyGuard heatmap jobs are asynchronous. Raise POLL_MAX_ATTEMPTS in backend/.env if large areas routinely need longer.",
      true,
    ),
  },
  {
    id: "agent-rate-limited",
    label: "Rate limited (503)",
    kind: "failure",
    latencyMs: 900,
    failure: failure(
      503,
      "agent_rate_limited",
      "The reasoning service is rate-limited. Try again in about 20 seconds.",
      "Groq's free tier limits requests per minute. openai/gpt-oss-120b has more headroom if this happens during a demo.",
      true,
    ),
  },
  {
    id: "not-configured",
    label: "Not configured (500)",
    kind: "failure",
    latencyMs: 500,
    failure: failure(
      500,
      "fortyguard_not_configured",
      "This server has no FortyGuard API key, so it cannot read temperatures.",
      "Set FORTYGUARD_API_KEY in backend/.env and restart uvicorn.",
      // The one scenario that must NOT offer a retry: pressing the button again cannot
      // conjure an API key, and a "Try again" button there is a lie.
      false,
    ),
  },
];

export const DEFAULT_MOCK_SCENARIO: MockScenarioId = "high";

/**
 * Whether the dashboard should answer from `MOCK_SCENARIOS` instead of the backend.
 *
 * Uses `NEXT_PUBLIC_USE_MOCK_DATA` which is inlined into the client bundle by the `env` block
 * in `next.config.ts`. This is the standard Next.js convention for client-accessible env vars.
 *
 * Read through full `process.env.X` member expressions — Next substitutes these literally at
 * build time, so destructuring or dynamic indexing would silently yield `undefined`.
 */
export function isMockMode(): boolean {
  const flag = process.env.NEXT_PUBLIC_USE_MOCK_DATA || "";
  return ["1", "true", "yes", "on"].includes(flag.trim().toLowerCase());
}

export function findScenario(id: MockScenarioId): MockScenario {
  return MOCK_SCENARIOS.find((scenario) => scenario.id === id) ?? MOCK_SCENARIOS[0];
}

/**
 * Play one scenario: wait out its latency, then hand back a stamped response or the failure.
 *
 * `evaluated_at` is stamped at call time rather than baked into the sample, so repeated
 * clicks build a history list with distinct entries — the thing you actually need in order to
 * lay that list out. It is generated inside an event handler, never during render, so it
 * cannot desynchronise server and client HTML.
 */
export async function playScenario(
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

/** A cancellable sleep, so an aborted evaluation stops waiting instead of resolving late. */
function delay(ms: number, signal?: AbortSignal): Promise<void> {
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
