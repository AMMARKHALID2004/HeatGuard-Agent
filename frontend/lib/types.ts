/** Contract mirrored from `backend/app/schemas.py`. Keep the two in sync. */

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "UNKNOWN";
export type Decision = "PROCEED" | "MODIFY" | "RESCHEDULE" | "NO_DATA";

/** `[longitude, latitude]` in WGS84 degrees. */
export type Coordinate = [number, number];

export interface EvaluateRequest {
  polygon_aoi: Coordinate[];
  date_time: string;
  /**
   * USPS state code of the work site, used server-side to resolve the climate zone.
   * Omit or send null to fall back to the default zone.
   */
  state?: string | null;
  /** FortyGuard analysis-layer selector. Omit to use the backend default (1). */
  filter_type?: number;
  /** FortyGuard grid granularity. Omit to use the backend default (100). */
  granularity?: number;
}

/**
 * The climate zone the backend resolved for an evaluation, plus the exact thresholds it
 * applied. Resolved server-side (`backend/app/climate.py`) and returned so the dashboard can
 * show which rules were used — the frontend never recomputes these.
 */
export interface ClimateZoneInfo {
  name: string;
  /** LOW/MEDIUM boundary, peak °C. */
  medium_threshold_c: number;
  /** MEDIUM/HIGH boundary, peak °C. */
  high_threshold_c: number;
}

/** The strict agent output (CLAUDE.md → Conventions). Temperatures are nullable. */
export interface AgentDecision {
  risk_level: RiskLevel;
  peak_temperature: number | null;
  average_temperature: number | null;
  decision: Decision;
  recommendation: string;
  reason: string;
}

/** What `POST /api/evaluate` returns: the decision plus request metadata. */
export interface EvaluateResponse extends AgentDecision {
  /** The climate zone resolved for this site, and the thresholds it applied. */
  climate_zone: ClimateZoneInfo;
  activity_id: string | null;
  evaluated_at: string;
  alert_sent: boolean;
}

/**
 * One US location suggestion from `GET /api/geocode`, already tagged with its resolved
 * climate zone so the dashboard can preview which thresholds it will use.
 */
export interface GeocodeResult {
  label: string;
  lat: number;
  lon: number;
  state: string | null;
  climate_zone: ClimateZoneInfo;
}

/**
 * A location the user has chosen to evaluate. Client-side state, not a wire type: the AOI ring
 * is generated locally around the picked point, and `state` is forwarded to the backend so it
 * resolves the same zone the suggestion previewed.
 */
export interface SelectedLocation {
  label: string;
  lat: number;
  lon: number;
  state: string | null;
  /** Closed `[lon, lat]` ring generated around the point (see `lib/demo.ts`). */
  aoi: Coordinate[];
}

/** Mirrors `backend/app/errors.py`. Every non-2xx, 422 included, has this shape. */
export type ApiErrorCode =
  | "invalid_request"
  | "fortyguard_not_configured"
  | "fortyguard_timeout"
  | "fortyguard_failed"
  | "fortyguard_unreachable"
  | "agent_not_configured"
  | "agent_rate_limited"
  | "agent_timeout"
  | "agent_failed"
  | "geocode_failed";

export interface ErrorDetail {
  code: ApiErrorCode;
  /** Written for the person looking at the dashboard. Safe to render as-is. */
  message: string;
  /** Where to look to fix it. Never contains upstream text, so never a leaked key. */
  hint: string;
  /** Whether repeating the identical request could plausibly succeed. */
  retryable: boolean;
}

export interface ApiErrorBody {
  /** Duplicates `error.message`, for clients that only read FastAPI's default body. */
  detail: string;
  error: ErrorDetail;
}
