"""OpenStreetMap Nominatim geocoding, proxied so a descriptive User-Agent can be sent.

The dashboard's "search any US location" box cannot call Nominatim directly: browsers
forbid setting a custom `User-Agent` on `fetch`/XHR, and Nominatim's usage policy asks for
a descriptive one that identifies the app. So the search runs here, server-side, and each
suggestion is tagged with its resolved climate zone (`app.climate`) before it reaches the
browser — the zone table stays server-only.

Keyless: Nominatim needs no API key, so this adds no secret. Results are limited to the US
(`countrycodes=us`) to match the climate-zone table.
"""

import logging
from typing import Any

import httpx

from ..climate import resolve_zone, state_code_from_nominatim
from ..config import Settings
from ..schemas import ClimateZoneInfo, GeocodeResult

logger = logging.getLogger(__name__)

# Nominatim policy asks for an identifying User-Agent. Browsers can't set one; this can.
USER_AGENT = "HeatGuard-Agent/0.1 (FortyGuard Hackathon 2026)"

# Below this length a query is not worth a round trip (and Nominatim rate-limits hard).
_MIN_QUERY_LENGTH = 2
_RESULT_LIMIT = 5


class GeocodeError(RuntimeError):
    """Nominatim was unreachable or returned something unusable."""


async def search(
    query: str,
    settings: Settings,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> list[GeocodeResult]:
    """Search US locations matching `query`, each tagged with its climate zone.

    Returns at most `_RESULT_LIMIT` suggestions, or `[]` for a blank/too-short query.
    Raises `GeocodeError` if Nominatim is unreachable or returns a non-2xx / unusable body.
    Pass `http_client` to inject one — that is how the tests supply an `httpx.MockTransport`.
    """
    query = query.strip()
    if len(query) < _MIN_QUERY_LENGTH:
        return []

    params = {
        "q": query,
        "countrycodes": "us",
        "format": "jsonv2",
        "addressdetails": "1",
        "limit": str(_RESULT_LIMIT),
    }
    headers = {"User-Agent": USER_AGENT}

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=settings.http_timeout_seconds)
    try:
        try:
            response = await client.get(
                f"{settings.nominatim_base_url}/search", params=params, headers=headers
            )
        except httpx.HTTPError as exc:
            raise GeocodeError(f"could not reach Nominatim: {exc}") from exc

        if response.is_error:
            raise GeocodeError(
                f"Nominatim returned HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            hits = response.json()
        except ValueError as exc:
            raise GeocodeError(f"Nominatim returned a non-JSON body: {exc}") from exc
    finally:
        if owns_client:
            await client.aclose()

    if not isinstance(hits, list):
        raise GeocodeError(
            f"expected a JSON array from Nominatim, got {type(hits).__name__}"
        )

    results = [result for hit in hits if (result := _to_result(hit)) is not None]
    logger.info("Geocode %r -> %s result(s)", query, len(results))
    return results


def _to_result(hit: Any) -> GeocodeResult | None:
    """Convert one Nominatim hit into a zoned `GeocodeResult`, or `None` if unusable."""
    if not isinstance(hit, dict):
        return None
    try:
        lat = float(hit["lat"])
        lon = float(hit["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    address = hit.get("address")
    address = address if isinstance(address, dict) else {}
    state = state_code_from_nominatim(address)
    zone = resolve_zone(state)
    return GeocodeResult(
        label=_label(hit, address),
        lat=lat,
        lon=lon,
        state=state,
        climate_zone=ClimateZoneInfo.from_zone(zone),
    )


def _label(hit: dict, address: dict) -> str:
    """A short "City, State" label, falling back to Nominatim's full display name."""
    primary = (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("hamlet")
        or address.get("suburb")
        or address.get("county")
        or hit.get("name")
    )
    region = address.get("state")
    if primary and region:
        return f"{primary}, {region}"
    return str(hit.get("display_name") or primary or region or "Unknown location")
