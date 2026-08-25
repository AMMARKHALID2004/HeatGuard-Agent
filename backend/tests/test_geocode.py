"""Tests for `app.services.geocode` and the `GET /api/geocode` route.

The search box can't call Nominatim directly (browsers forbid a custom `User-Agent`), so it
goes through the backend. Two layers under test:

- `SearchServiceTests` drive the real `search()` over an `httpx.MockTransport` with realistic
  Nominatim payloads — the request it sends (policy User-Agent, `countrycodes=us`) and the
  zoned results it parses back.
- `GeocodeRouteTests` patch the service to check the route's own contract: the list shape on
  success, and the `502 geocode_failed` it raises on a `GeocodeError`, in the same error
  envelope as the rest of the API.

    uv run python -m unittest discover -v
"""

import unittest
from typing import Any
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.routers import evaluate as evaluate_router
from app.schemas import ClimateZoneInfo, GeocodeResult
from app.services.geocode import USER_AGENT, GeocodeError, search

NOMINATIM_BASE_URL = "https://nominatim.test"

# Realistic Nominatim `format=jsonv2&addressdetails=1` hits.
PHOENIX = {
    "lat": "33.4484",
    "lon": "-112.0740",
    "name": "Phoenix",
    "display_name": "Phoenix, Maricopa County, Arizona, United States",
    "address": {"city": "Phoenix", "state": "Arizona", "ISO3166-2-lvl4": "US-AZ"},
}
MIAMI = {
    "lat": "25.7617",
    "lon": "-80.1918",
    "name": "Miami",
    "display_name": "Miami, Miami-Dade County, Florida, United States",
    "address": {"city": "Miami", "state": "Florida", "ISO3166-2-lvl4": "US-FL"},
}


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "fortyguard_api_key": "fg-test",
        "groq_api_key": "gq-test",
        "nominatim_base_url": NOMINATIM_BASE_URL,
        "http_timeout_seconds": 5.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class SearchServiceTests(unittest.IsolatedAsyncioTestCase):
    def _client(self, handler: Any) -> httpx.AsyncClient:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(client.aclose)
        return client

    async def test_a_realistic_payload_becomes_zoned_results(self):
        client = self._client(lambda r: httpx.Response(200, json=[PHOENIX, MIAMI]))

        results = await search("phoenix", make_settings(), http_client=client)

        self.assertEqual(len(results), 2)
        phx = results[0]
        self.assertEqual(phx.label, "Phoenix, Arizona")
        self.assertEqual(phx.state, "AZ")
        self.assertEqual(phx.climate_zone.name, "Hot-Dry")
        self.assertAlmostEqual(phx.lat, 33.4484)
        self.assertAlmostEqual(phx.lon, -112.0740)
        # A second location resolves to its own zone — the mapping isn't a constant.
        self.assertEqual(results[1].label, "Miami, Florida")
        self.assertEqual(results[1].climate_zone.name, "Hot-Humid")

    async def test_it_sends_the_policy_user_agent_and_the_us_filter(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=[PHOENIX])

        await search("phoenix", make_settings(), http_client=self._client(handler))

        request = seen[0]
        # CLAUDE.md / Nominatim policy: identify the app. This is why we proxy at all.
        self.assertEqual(request.headers["user-agent"], USER_AGENT)
        self.assertEqual(request.url.params["countrycodes"], "us")
        self.assertEqual(request.url.params["q"], "phoenix")
        self.assertEqual(request.url.params["format"], "jsonv2")
        self.assertEqual(request.url.params["addressdetails"], "1")
        self.assertEqual(request.url.params["limit"], "5")
        self.assertTrue(str(request.url).startswith(f"{NOMINATIM_BASE_URL}/search"))

    async def test_a_blank_or_too_short_query_returns_empty_without_a_round_trip(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json=[PHOENIX])

        client = self._client(handler)
        for query in ("", "   ", "a", " a "):
            with self.subTest(query=repr(query)):
                self.assertEqual(await search(query, make_settings(), http_client=client), [])
        self.assertEqual(seen, [], "a too-short query must not hit the rate-limited API")

    async def test_unusable_hits_are_skipped_rather_than_failing_the_search(self):
        no_coords = {"name": "somewhere", "address": {}}
        client = self._client(lambda r: httpx.Response(200, json=[no_coords, PHOENIX]))

        results = await search("phoenix", make_settings(), http_client=client)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].state, "AZ")

    async def test_an_http_error_status_becomes_a_geocode_error(self):
        client = self._client(lambda r: httpx.Response(500, text="upstream boom"))

        with self.assertRaises(GeocodeError):
            await search("phoenix", make_settings(), http_client=client)

    async def test_a_non_json_body_becomes_a_geocode_error(self):
        client = self._client(
            lambda r: httpx.Response(
                200, content=b"<html>nope</html>", headers={"content-type": "text/html"}
            )
        )

        with self.assertRaises(GeocodeError):
            await search("phoenix", make_settings(), http_client=client)

    async def test_a_non_list_json_becomes_a_geocode_error(self):
        client = self._client(lambda r: httpx.Response(200, json={"error": "nope"}))

        with self.assertRaises(GeocodeError):
            await search("phoenix", make_settings(), http_client=client)

    async def test_a_transport_failure_becomes_a_geocode_error(self):
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        with self.assertRaises(GeocodeError):
            await search("phoenix", make_settings(), http_client=self._client(boom))


class GeocodeRouteTests(unittest.TestCase):
    def client(self, **overrides: Any) -> TestClient:
        settings = make_settings(**overrides)
        app.dependency_overrides[get_settings] = lambda: settings
        self.addCleanup(app.dependency_overrides.clear)
        return TestClient(app)

    def test_it_returns_the_zoned_suggestions(self):
        async def fake(q: str, settings: Settings, **kw: Any) -> list[GeocodeResult]:
            zone = ClimateZoneInfo(name="Hot-Dry", medium_threshold_c=36.0, high_threshold_c=39.0)
            return [
                GeocodeResult(
                    label="Phoenix, Arizona", lat=33.4484, lon=-112.074, state="AZ",
                    climate_zone=zone,
                )
            ]

        with patch.object(evaluate_router, "geocode_search", fake):
            response = self.client().get("/api/geocode", params={"q": "phoenix"})

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["label"], "Phoenix, Arizona")
        self.assertEqual(body[0]["state"], "AZ")
        self.assertEqual(body[0]["climate_zone"]["name"], "Hot-Dry")
        self.assertEqual(body[0]["climate_zone"]["high_threshold_c"], 39.0)

    def test_a_geocode_error_maps_to_502_in_the_standard_error_envelope(self):
        async def boom(q: str, settings: Settings, **kw: Any) -> list[GeocodeResult]:
            raise GeocodeError("nominatim unreachable")

        with patch.object(evaluate_router, "geocode_search", boom):
            response = self.client().get("/api/geocode", params={"q": "phoenix"})

        self.assertEqual(response.status_code, 502, response.text)
        body = response.json()
        self.assertEqual(body["error"]["code"], "geocode_failed")
        self.assertTrue(body["error"]["retryable"])
        # The same shape every other error uses, so the dashboard renders it identically.
        self.assertEqual(set(body["error"]), {"code", "message", "hint", "retryable"})
        self.assertEqual(body["detail"], body["error"]["message"])
        # And nothing raw from the upstream leaks into what the browser sees.
        self.assertNotIn("nominatim unreachable", response.text)

    def test_a_missing_query_is_rejected(self):
        response = self.client().get("/api/geocode")

        self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
