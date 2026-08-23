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
