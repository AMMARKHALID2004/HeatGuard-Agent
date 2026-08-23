"""`POST /api/evaluate` — the agent loop the dashboard triggers.

FortyGuard heatmap job -> `HeatRiskAgent` (measure, reason, enforce thresholds) -> Slack
alert on RESCHEDULE.
"""

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from ..agent import AgentError, HeatRiskAgent
from ..config import Settings, get_settings
from ..schemas import EvaluateRequest, EvaluateResponse
from ..services import slack
from ..services.fortyguard import FortyGuardClient, FortyGuardError, FortyGuardTimeout

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agent"])


@router.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(
    request: EvaluateRequest,
    settings: Settings = Depends(get_settings),
) -> EvaluateResponse:
    try:
        async with FortyGuardClient(settings) as fortyguard:
            activity_id, heatmap = await fortyguard.fetch_heatmap(
                polygon_aoi=request.polygon_aoi,
                date_time=request.date_time,
                filter_type=request.filter_type,
                granularity=request.granularity,
            )
    except FortyGuardTimeout as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, str(exc)) from exc
    except FortyGuardError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"could not reach FortyGuard: {exc}"
        ) from exc

    try:
        async with HeatRiskAgent(settings) as agent:
            decision = await agent.assess(heatmap, date_time=request.date_time)
    except AgentError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    alert_sent = False
    if decision.decision == "RESCHEDULE":
        alert_sent = await slack.send_alert(settings, decision)

    logger.info(
        "Evaluation complete: activity_id=%s risk=%s decision=%s peak=%s alert_sent=%s",
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
