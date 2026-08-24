"""`POST /api/evaluate` — the agent loop the dashboard triggers.

FortyGuard heatmap job -> `HeatRiskAgent` (measure, reason, enforce thresholds) -> Slack
alert on RESCHEDULE.

The whole body runs under one `try`, and every failure is translated by `app.errors` into a
displayable sentence. Nothing that goes wrong after a decision exists is allowed to discard
it: Slack alerting is best-effort, so a broken webhook downgrades `alert_sent` to `false`
and the decision still reaches the dashboard.
"""

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, status

from ..agent import AgentError, HeatRiskAgent
from ..config import Settings, get_settings
from ..errors import as_api_error
from ..schemas import ErrorResponse, EvaluateRequest, EvaluateResponse
from ..services import slack
from ..services.fortyguard import FortyGuardClient, FortyGuardError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agent"])

# Documented in OpenAPI so the dashboard's error handling is written against the contract
# rather than against whatever it happened to see during development.
_ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    # 422 as a literal: Starlette deprecated `HTTP_422_UNPROCESSABLE_ENTITY`.
    422: {
        "model": ErrorResponse,
        "description": "The AOI or timestamp could not be read.",
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorResponse,
        "description": "A required API key is missing from the server's environment.",
    },
    status.HTTP_502_BAD_GATEWAY: {
        "model": ErrorResponse,
        "description": "FortyGuard rejected the request, or Groq never returned a valid decision.",
    },
    status.HTTP_503_SERVICE_UNAVAILABLE: {
        "model": ErrorResponse,
        "description": "Groq rate-limited the request. Carries `Retry-After` when Groq sent one.",
    },
    status.HTTP_504_GATEWAY_TIMEOUT: {
        "model": ErrorResponse,
        "description": "The heatmap job or the reasoning phase ran out of time.",
    },
}


@router.post(
    "/evaluate",
    response_model=EvaluateResponse,
    responses=_ERROR_RESPONSES,
    summary="Assess heat risk for one area and work window",
)
async def evaluate(
    request: EvaluateRequest,
    settings: Settings = Depends(get_settings),
) -> EvaluateResponse:
    """Read the area's temperatures, assess them, and return a go/no-go decision."""
    started = datetime.now(timezone.utc)
    try:
        async with FortyGuardClient(settings) as fortyguard:
            activity_id, heatmap = await fortyguard.fetch_heatmap(
                polygon_aoi=request.polygon_aoi,
                date_time=request.date_time,
                filter_type=request.filter_type,
                granularity=request.granularity,
            )

        async with HeatRiskAgent(settings) as agent:
            decision = await agent.assess(heatmap, date_time=request.date_time)
    except (FortyGuardError, AgentError, httpx.HTTPError, httpx.InvalidURL) as exc:
        # `as_api_error` re-raises anything it does not recognise, so an unexpected
        # exception still surfaces as a 500 with a traceback rather than being flattened
        # into a misleading 502. `httpx.InvalidURL` is listed separately on purpose: it
        # does *not* inherit from `httpx.HTTPError` (verified against httpx 0.28), which is
        # exactly the trap that let a malformed webhook URL escape the Slack handler.
        raise as_api_error(exc) from exc

    # Past this point a decision exists, and returning it matters more than anything left.
    alert_sent = False
    if decision.decision == "RESCHEDULE":
        alert_sent = await slack.send_alert(settings, decision)

    logger.info(
        "Evaluation complete in %.1fs: activity_id=%s risk=%s decision=%s peak=%s alert_sent=%s",
        (datetime.now(timezone.utc) - started).total_seconds(),
        activity_id,
        decision.risk_level,
        decision.decision,
        decision.peak_temperature,
        alert_sent,
    )

    return EvaluateResponse(
        **decision.model_dump(),
        activity_id=activity_id,
        evaluated_at=datetime.now(timezone.utc),
        alert_sent=alert_sent,
    )
