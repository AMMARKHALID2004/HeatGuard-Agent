"""`POST /api/evaluate` — the agent loop the dashboard triggers.

FortyGuard heatmap job -> `HeatRiskAgent` (measure, reason, enforce thresholds) -> Slack
alert on RESCHEDULE.

The whole body runs under one `try`, and every failure is translated by `app.errors` into a
displayable sentence. Nothing that goes wrong after a decision exists is allowed to discard
it: Slack alerting is best-effort, so a broken webhook downgrades `alert_sent` to `false`
and the decision still reaches the dashboard.
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Query, status

from ..agent import AgentError, HeatRiskAgent
from ..climate import resolve_zone
from ..config import Settings, get_settings
from ..errors import ApiError, as_api_error
from ..schemas import (
    ClimateZoneInfo,
    ErrorResponse,
    EvaluateRequest,
    EvaluateResponse,
    GeocodeResult,
)
from ..services import slack
from ..services.fortyguard import FortyGuardClient, FortyGuardError
from ..services.geocode import GeocodeError, search as geocode_search
from ..services.heatmap import summarize_heatmap

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agent"])

# FortyGuard's own accepted range (confirmed by their team, 2026-08): 2021-01-01 through
# now+12h. The step-back fallback below must never wander earlier than this, or a "Now"
# request near the start of that range could turn a valid request into a rejected one.
_FORTYGUARD_MIN_DATE = datetime(2021, 1, 1)


async def _fetch_heatmap_with_fallback(
    fortyguard: FortyGuardClient,
    *,
    polygon_aoi: list[list[float]],
    date_time: datetime,
    filter_type: int,
    granularity: int,
    settings: Settings,
) -> tuple[str, object, datetime, int]:
    """Fetch a heatmap, stepping the timestamp backward if it comes back with no readings.

    FortyGuard's data is satellite-derived: the API accepts any request in its documented
    range 24/7, but the literal current instant can still fall in a gap between passes
    before that imagery is processed, even though the request itself was valid. A request
    for a few minutes or hours earlier is often already backed by a completed reading — so
    rather than surface that processing gap as a false "no data" MODIFY floor, retry the
    *same* AOI a little further back in time. Every reading returned is still real
    FortyGuard data; this only chooses which recent instant to ask for.

    Returns `(activity_id, heatmap, date_time_used, steps_back)`. `steps_back` is 0 when
    the first, originally-requested timestamp already had data (or the fallback is
    disabled/exhausted), so callers can tell whether the timestamp changed.
    """
    step = timedelta(minutes=settings.now_fallback_step_minutes)
    max_steps = max(0, settings.now_fallback_max_steps)

    current = date_time
    for attempt in range(max_steps + 1):
        activity_id, heatmap = await fortyguard.fetch_heatmap(
            polygon_aoi=polygon_aoi,
            date_time=current,
            filter_type=filter_type,
            granularity=granularity,
        )
        summary = summarize_heatmap(heatmap)
        if summary["reading_count"] > 0 or attempt == max_steps:
            if attempt > 0:
                logger.info(
                    "Heatmap had no readings at %s; found data %s step(s) back at %s",
                    date_time.isoformat(),
                    attempt,
                    current.isoformat(),
                )
            return activity_id, heatmap, current, attempt

        candidate = current - step
        if candidate < _FORTYGUARD_MIN_DATE:
            # Stepping further back would leave FortyGuard's accepted range — stop here
            # and let the caller handle the (still real) empty result.
            return activity_id, heatmap, current, attempt
        current = candidate

    # Unreachable (the loop always returns on its last iteration), kept for type-checkers.
    return activity_id, heatmap, current, max_steps


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
    zone = resolve_zone(request.state)
    try:
        async with FortyGuardClient(settings) as fortyguard:
            activity_id, heatmap, effective_date_time, steps_back = (
                await _fetch_heatmap_with_fallback(
                    fortyguard,
                    polygon_aoi=request.polygon_aoi,
                    date_time=request.date_time,
                    filter_type=request.filter_type,
                    granularity=request.granularity,
                    settings=settings,
                )
            )

        async with HeatRiskAgent(settings) as agent:
            decision = await agent.assess(
                heatmap, date_time=effective_date_time, zone=zone
            )
    except (FortyGuardError, AgentError, httpx.HTTPError, httpx.InvalidURL) as exc:
        # `as_api_error` re-raises anything it does not recognise, so an unexpected
        # exception still surfaces as a 500 with a traceback rather than being flattened
        # into a misleading 502. `httpx.InvalidURL` is listed separately on purpose: it
        # does *not* inherit from `httpx.HTTPError` (verified against httpx 0.28), which is
        # exactly the trap that let a malformed webhook URL escape the Slack handler.
        raise as_api_error(exc) from exc

    # If the requested instant had no reading and a nearby one did, say so on the card —
    # the reading is still real FortyGuard data, just for a slightly earlier timestamp than
    # what was asked for. Prepended rather than replacing `reason`, so the threshold
    # explanation underneath is unchanged. Gated on `peak_temperature is not None`, not
    # just `steps_back > 0`: the fallback budget can also be exhausted with *no* step ever
    # finding data, and that's the genuine no-data case — its own fail-safe message
    # (`risk.UNMEASURABLE_REASON`) already covers it correctly and shouldn't be prefixed
    # with a claim that an earlier reading was found when none was.
    if steps_back > 0 and decision.peak_temperature is not None:
        minutes_back = round(steps_back * settings.now_fallback_step_minutes)
        hours_back = minutes_back / 60
        span = f"{hours_back:g}h" if minutes_back % 60 == 0 else f"{minutes_back}m"
        decision = decision.model_copy(
            update={
                "reason": (
                    f"No FortyGuard reading was available for the exact requested time, so "
                    f"this uses the most recent available reading, {span} earlier. "
                    f"{decision.reason}"
                )
            }
        )

    # Past this point a decision exists, and returning it matters more than anything left.
    alert_sent = False
    if decision.decision == "RESCHEDULE":
        alert_sent = await slack.send_alert(settings, decision)

    logger.info(
        "Evaluation complete in %.1fs: activity_id=%s zone=%s risk=%s decision=%s peak=%s "
        "alert_sent=%s steps_back=%s",
        (datetime.now(timezone.utc) - started).total_seconds(),
        activity_id,
        zone.name,
        decision.risk_level,
        decision.decision,
        decision.peak_temperature,
        alert_sent,
        steps_back,
    )

    return EvaluateResponse(
        **decision.model_dump(),
        climate_zone=ClimateZoneInfo.from_zone(zone),
        activity_id=activity_id,
        evaluated_at=datetime.now(timezone.utc),
        alert_sent=alert_sent,
    )


@router.get(
    "/geocode",
    response_model=list[GeocodeResult],
    responses={
        status.HTTP_502_BAD_GATEWAY: {
            "model": ErrorResponse,
            "description": "The location search service was unreachable or returned an error.",
        },
    },
    summary="Search US locations, each tagged with its climate zone",
)
async def geocode(
    q: str = Query(..., description="Free-text US location query, e.g. 'Phoenix'."),
    settings: Settings = Depends(get_settings),
) -> list[GeocodeResult]:
    """Suggest US locations for the search box, resolving each one's climate zone."""
    try:
        return await geocode_search(q, settings)
    except GeocodeError as exc:
        # A new endpoint, so it gets its own `ApiError` rather than routing through the
        # FortyGuard-flavored `as_api_error`. Same response shape, own code — the search
        # box degrades to "couldn't search" without touching the evaluate error contract.
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            code="geocode_failed",
            message="Couldn't search for locations right now. Please try again in a moment.",
            hint="Nominatim was unreachable or returned an error; see the backend log.",
            retryable=True,
            cause=str(exc),
        ) from exc
