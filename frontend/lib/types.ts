/** Contract mirrored from `backend/app/schemas.py`. Keep the two in sync. */

export type RiskLevel = "LOW" | "MEDIUM" | "HIGH";
export type Decision = "PROCEED" | "MODIFY" | "RESCHEDULE";

/** `[longitude, latitude]` in WGS84 degrees. */
export type Coordinate = [number, number];

export interface EvaluateRequest {
  polygon_aoi: Coordinate[];
  date_time: string;
  /** FortyGuard analysis-layer selector. Omit to use the backend default (1). */
  filter_type?: number;
  /** FortyGuard grid granularity. Omit to use the backend default (100). */
  granularity?: number;
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
  activity_id: string | null;
  evaluated_at: string;
  alert_sent: boolean;
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
  | "agent_failed";

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
