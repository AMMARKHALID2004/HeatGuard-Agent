"""FortyGuard Temperature API client.

The API is submit-and-poll, not synchronous: `POST /v1/heatmap` returns an activity id,
and `GET /v1/status/{activity_id}` reports progress until the job completes. The poll loop
is bounded (max attempts + exponential backoff) and raises `FortyGuardTimeout` instead of
spinning forever — the n8n prototype's `If -> Wait -> Check Heatmap Status` cycle had no
attempt counter and could loop indefinitely.

Request and response shapes are taken from the validated prototype in
`n8n/heatguard-workflow.json`:

- `HTTP Request` node          -> the request body built by `build_heatmap_payload`
- `Check Heatmap Status` node  -> `$json.data.activity_id`
- `If` node                    -> `$json.data.status == "Completed"`
- `Edit Fields` node           -> the heatmap itself is `$json.data.result`

So every response is wrapped in a `data` envelope; `_envelope` unwraps it.

TODO(fortyguard-docs): `filter_type` and `granularity` default to the prototype's
validated values (1 and 100). Confirm what `filter_type` selects — it is the likely control
for the snapshot / exceedance / persistence analysis layer, and a shift-level go/no-go call
wants the snapshot (peak) layer.
"""

import asyncio
import logging
from datetime import datetime
from types import TracebackType
from typing import Any, Self

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)

# Compared case-insensitively against `data.status`. The prototype matched the exact
# string "Completed"; the extra spellings are cheap insurance.
COMPLETED_STATUSES = frozenset({"completed", "complete", "succeeded", "success", "finished"})
FAILED_STATUSES = frozenset({"failed", "error", "cancelled", "canceled"})

DEFAULT_FILTER_TYPE = 1
DEFAULT_GRANULARITY = 100


class FortyGuardError(RuntimeError):
    """FortyGuard rejected the request or returned something unusable."""


class FortyGuardTimeout(FortyGuardError, TimeoutError):
    """A job did not reach "Completed" within the bounded poll budget.

    Subclasses the builtin `TimeoutError` as well, so callers can catch either
    `FortyGuardError` (all upstream failures) or `TimeoutError` (just this one).
    """


def build_heatmap_payload(
    polygon_aoi: list[list[float]],
    date_time: datetime,
    *,
    filter_type: int = DEFAULT_FILTER_TYPE,
    granularity: int = DEFAULT_GRANULARITY,
) -> dict[str, Any]:
    """Translate the dashboard's plain ring + timestamp into FortyGuard's request shape.

    The AOI goes up as a GeoJSON FeatureCollection (a Polygon's `coordinates` is a list of
    rings, hence the extra nesting), and the timestamp is split into separate date and time
    fields.
    """
    return {
        "polygon_aoi": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {},
                    "geometry": {"type": "Polygon", "coordinates": [polygon_aoi]},
                }
            ],
        },
        "date_time": {
            "start_date": date_time.strftime("%Y-%m-%d"),
            "start_time": date_time.strftime("%H:%M"),
            "filter_type": filter_type,
        },
        "granularity": granularity,
    }


def _envelope(body: Any) -> dict[str, Any]:
    """Return the `data` object, tolerating a response that is already unwrapped."""
    if not isinstance(body, dict):
        raise FortyGuardError(
            f"expected a JSON object from FortyGuard, got {type(body).__name__}"
        )
    data = body.get("data")
    return data if isinstance(data, dict) else body


class FortyGuardClient:
    """Submit heatmap jobs and wait for their results.

    Owns an `httpx.AsyncClient` when used as an async context manager:

        async with FortyGuardClient(settings) as client:
            activity_id, heatmap = await client.fetch_heatmap(
                polygon_aoi=ring, date_time=when
            )

    Pass `http_client` to inject one instead — that is how the tests supply an
    `httpx.MockTransport`.
    """

    def __init__(self, settings: Settings, *, http_client: httpx.AsyncClient | None = None):
        self._settings = settings
        self._http = http_client
        self._owns_http = http_client is None

    async def __aenter__(self) -> Self:
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._settings.http_timeout_seconds)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    @property
    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            raise RuntimeError(
                "FortyGuardClient has no HTTP client: use it as an async context manager, "
                "or pass http_client="
            )
        return self._http

    def _request_headers(self) -> dict[str, str]:
        if not self._settings.fortyguard_api_key:
            raise FortyGuardError("FORTYGUARD_API_KEY is not set")
        return {"api-key": self._settings.fortyguard_api_key}

    async def submit_heatmap(
        self,
        *,
        polygon_aoi: list[list[float]],
        date_time: datetime,
        filter_type: int = DEFAULT_FILTER_TYPE,
        granularity: int = DEFAULT_GRANULARITY,
    ) -> str:
        """Kick off a heatmap job and return its `activity_id`."""
        response = await self._client.post(
            f"{self._settings.fortyguard_base_url}/heatmap",
            headers=self._request_headers(),
            json=build_heatmap_payload(
                polygon_aoi, date_time, filter_type=filter_type, granularity=granularity
            ),
        )
        if response.is_error:
            raise FortyGuardError(
                f"heatmap submit failed with HTTP {response.status_code}: {response.text[:300]}"
            )

        data = _envelope(response.json())
        activity_id = data.get("activity_id") or data.get("activityId") or data.get("id")
        if not activity_id:
            raise FortyGuardError(f"heatmap submit returned no activity_id: {data}")

        logger.info("FortyGuard job submitted: activity_id=%s", activity_id)
        return str(activity_id)

    async def poll_until_complete(self, activity_id: str) -> Any:
        """Poll a job until it completes and return `data.result`.

        Sleeps before each attempt (the job is never ready instantly), backing off by
        `poll_backoff_factor` up to `poll_max_delay_seconds`, for at most
        `poll_max_attempts` attempts.

        Raises `FortyGuardTimeout` if the budget runs out, or `FortyGuardError` if the job
        reports a failed status or completes without a result.
        """
        settings = self._settings
        delay = settings.poll_initial_delay_seconds
        waited = 0.0

        for attempt in range(1, settings.poll_max_attempts + 1):
            await asyncio.sleep(delay)
            waited += delay

            response = await self._client.get(
                f"{settings.fortyguard_base_url}/status/{activity_id}",
                headers=self._request_headers(),
            )
            if response.is_error:
                raise FortyGuardError(
                    f"status check failed with HTTP {response.status_code}: "
                    f"{response.text[:300]}"
                )

            data = _envelope(response.json())
            status = str(data.get("status", "")).strip().lower()
            logger.info(
                "FortyGuard poll %s/%s: activity_id=%s status=%s",
                attempt,
                settings.poll_max_attempts,
                activity_id,
                status or "<missing>",
            )

            if status in COMPLETED_STATUSES:
                if "result" not in data:
                    raise FortyGuardError(
                        f"job {activity_id} completed but carried no 'result' field "
                        f"(keys: {sorted(data)})"
                    )
                return data["result"]
            if status in FAILED_STATUSES:
                raise FortyGuardError(
                    f"FortyGuard job {activity_id} reported status '{status}'"
                )

            delay = min(delay * settings.poll_backoff_factor, settings.poll_max_delay_seconds)

        raise FortyGuardTimeout(
            f"FortyGuard job {activity_id} did not reach 'Completed' after "
            f"{settings.poll_max_attempts} status checks over {waited:.1f}s"
        )

    async def fetch_heatmap(
        self,
        *,
        polygon_aoi: list[list[float]],
        date_time: datetime,
        filter_type: int = DEFAULT_FILTER_TYPE,
        granularity: int = DEFAULT_GRANULARITY,
    ) -> tuple[str, Any]:
        """Submit a job, wait for it, and return `(activity_id, heatmap_result)`."""
        activity_id = await self.submit_heatmap(
            polygon_aoi=polygon_aoi,
            date_time=date_time,
            filter_type=filter_type,
            granularity=granularity,
        )
        return activity_id, await self.poll_until_complete(activity_id)
