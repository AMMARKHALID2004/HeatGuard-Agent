"""`POST /api/evaluate` — the agent loop the dashboard triggers.

FortyGuard heatmap job -> temperature summary -> Groq reasoning -> threshold enforcement
-> Slack alert on RESCHEDULE.
"""

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from ..config import Settings, get_settings
from ..risk import enforce_thresholds
from ..schemas import EvaluateRequest, EvaluateResponse
from ..services import slack
from ..services.fortyguard import FortyGuardClient, FortyGuardError, FortyGuardTimeout
from ..services.heatmap import summarize_heatmap
from ..services.llm import LLMError, reason_about_heat

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

    summary = summarize_heatmap(heatmap)
    logger.info(
        "Heatmap summarized: activity_id=%s readings=%s peak=%s",
        activity_id,
        summary["reading_count"],
        summary["peak_temperature"],
    )

    try:
        decision = await reason_about_heat(
            settings, summary=summary, date_time=request.date_time
        )
    except LLMError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"could not reach Groq: {exc}") from exc

    decision = enforce_thresholds(decision)

    alert_sent = False
    if decision.decision == "RESCHEDULE":
        alert_sent = await slack.send_alert(settings, decision)

    return EvaluateResponse(
        **decision.model_dump(),
        activity_id=activity_id,
        evaluated_at=datetime.now(timezone.utc),
        alert_sent=alert_sent,
    )
