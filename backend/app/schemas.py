"""Request/response contracts shared with the dashboard."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]
Decision = Literal["PROCEED", "MODIFY", "RESCHEDULE"]


class EvaluateRequest(BaseModel):
    """Input from the dashboard. Both fields are real parameters, never hardcoded.

    This is the plain shape the dashboard speaks; `services.fortyguard` translates it into
    FortyGuard's GeoJSON + split date/time request body.
    """

    polygon_aoi: list[list[float]] = Field(
        ...,
        min_length=3,
        description="AOI ring as [[lon, lat], ...] in WGS84 degrees.",
    )
    date_time: datetime = Field(
        ...,
        description="Start of the work window being evaluated, ISO 8601.",
    )
    filter_type: int = Field(
        1,
        description=(
            "FortyGuard analysis-layer selector, passed through as-is. Defaults to the "
            "value the n8n prototype validated."
        ),
    )
    granularity: int = Field(
        100,
        gt=0,
        description="FortyGuard grid granularity. Defaults to the prototype's value.",
    )

    @field_validator("polygon_aoi")
    @classmethod
    def _validate_ring(cls, ring: list[list[float]]) -> list[list[float]]:
        for vertex in ring:
            if len(vertex) != 2:
                raise ValueError("each AOI vertex must be a [lon, lat] pair")
            lon, lat = vertex
            if not -180.0 <= lon <= 180.0:
                raise ValueError(f"longitude out of range in vertex {vertex}")
            if not -90.0 <= lat <= 90.0:
                raise ValueError(f"latitude out of range in vertex {vertex}")
        return ring


class AgentDecision(BaseModel):
    """The strict JSON the agent produces (CLAUDE.md → Conventions).

    `peak_temperature` / `average_temperature` are null when the heatmap carried no
    usable temperature values — the agent reports missing data rather than inventing it.
    """

    risk_level: RiskLevel
    peak_temperature: float | None = None
    average_temperature: float | None = None
    decision: Decision
    recommendation: str
    reason: str


class EvaluateResponse(AgentDecision):
    """`AgentDecision` plus request-scoped metadata the dashboard uses for history."""

    activity_id: str | None = None
    evaluated_at: datetime
    alert_sent: bool = False


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    fortyguard_configured: bool
    groq_configured: bool
    slack_configured: bool
