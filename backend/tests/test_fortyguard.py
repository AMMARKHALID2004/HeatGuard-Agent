"""Tests for `app.services.fortyguard.FortyGuardClient`.

Uses `httpx.MockTransport` — httpx's own mock — injected via the client's `http_client`
parameter, so the real request-building and poll-loop code runs against scripted responses.

`unittest.IsolatedAsyncioTestCase` keeps this dependency-free (pytest will also collect it
if it gets added later):

    uv run python -m unittest discover -v
"""

import asyncio
import json
import unittest
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx

from app.config import Settings
from app.services.fortyguard import (
    FortyGuardClient,
    FortyGuardError,
    FortyGuardTimeout,
)

BASE_URL = "https://api.fortyguard.com/v1"
API_KEY = "test-key"
ACTIVITY_ID = "act-123"

# The AOI and work window the n8n prototype validated.
RING = [
    [-74.017, 40.705],
    [-74.003, 40.705],
    [-74.003, 40.718],
    [-74.017, 40.718],
    [-74.017, 40.705],
]
WHEN = datetime(2024, 7, 15, 14, 0)

HEATMAP_RESULT = {"cells": [{"temperature": 41.2}, {"temperature": 38.4}]}

SUBMIT_OK = (200, {"data": {"activity_id": ACTIVITY_ID}})
STATUS_PROCESSING = (200, {"data": {"status": "Processing"}})
STATUS_COMPLETED = (200, {"data": {"status": "Completed", "result": HEATMAP_RESULT}})


def make_settings(**overrides: Any) -> Settings:
    """Test settings with polling delays zeroed out, ignoring any real `.env`."""
    values: dict[str, Any] = {
        "fortyguard_api_key": API_KEY,
        "fortyguard_base_url": BASE_URL,
        "poll_max_attempts": 15,
        "poll_initial_delay_seconds": 0.0,
        "poll_backoff_factor": 1.5,
        "poll_max_delay_seconds": 0.0,
        "http_timeout_seconds": 5.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


class ScriptedFortyGuard:
    """A `MockTransport` handler that scripts `/heatmap` and `/status` and records calls.

    `statuses` is consumed in order; the last entry repeats for any further polls, which is
    what lets a single entry stand in for "always Processing".
    """

    def __init__(
        self,
        *,
        submit: tuple[int, Any] = SUBMIT_OK,
        statuses: list[tuple[int, Any]] | None = None,
    ):
        self.submit = submit
        self.statuses = statuses or [STATUS_COMPLETED]
        self.heatmap_requests: list[httpx.Request] = []
        self.status_requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/heatmap"):
            self.heatmap_requests.append(request)
            code, payload = self.submit
            return httpx.Response(code, json=payload)

        self.status_requests.append(request)
        index = min(len(self.status_requests) - 1, len(self.statuses) - 1)
        code, payload = self.statuses[index]
        return httpx.Response(code, json=payload)

    @property
    def poll_count(self) -> int:
        return len(self.status_requests)


class FortyGuardClientTestCase(unittest.IsolatedAsyncioTestCase):
    def build(
        self, handler: ScriptedFortyGuard, **setting_overrides: Any
    ) -> FortyGuardClient:
        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        self.addAsyncCleanup(http.aclose)
        return FortyGuardClient(make_settings(**setting_overrides), http_client=http)


class SuccessTests(FortyGuardClientTestCase):
    async def test_returns_activity_id_and_result(self):
        api = ScriptedFortyGuard(statuses=[STATUS_PROCESSING, STATUS_COMPLETED])
        client = self.build(api)

        activity_id, result = await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertEqual(activity_id, ACTIVITY_ID)
        self.assertEqual(result, HEATMAP_RESULT)
        # Polled twice: once seeing Processing, once seeing Completed.
        self.assertEqual(api.poll_count, 2)

    async def test_sends_the_prototype_request_shape(self):
        api = ScriptedFortyGuard()
        client = self.build(api)

        await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        request = api.heatmap_requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(str(request.url), f"{BASE_URL}/heatmap")
        self.assertEqual(request.headers["api-key"], API_KEY)

        body = json.loads(request.content)
        self.assertEqual(body["polygon_aoi"]["type"], "FeatureCollection")
        geometry = body["polygon_aoi"]["features"][0]["geometry"]
        self.assertEqual(geometry["type"], "Polygon")
        # A Polygon's coordinates is a list of rings, so the ring is nested one deeper.
        self.assertEqual(geometry["coordinates"], [RING])
        self.assertEqual(
            body["date_time"],
            {"start_date": "2024-07-15", "start_time": "14:00", "filter_type": 1},
        )
        self.assertEqual(body["granularity"], 100)

    async def test_polls_the_status_url_for_the_returned_activity_id(self):
        api = ScriptedFortyGuard()
        client = self.build(api)

        await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertEqual(str(api.status_requests[0].url), f"{BASE_URL}/status/{ACTIVITY_ID}")
        self.assertEqual(api.status_requests[0].headers["api-key"], API_KEY)

    async def test_forwards_filter_type_and_granularity_overrides(self):
        api = ScriptedFortyGuard()
        client = self.build(api)

        await client.fetch_heatmap(
            polygon_aoi=RING, date_time=WHEN, filter_type=3, granularity=250
        )

        body = json.loads(api.heatmap_requests[0].content)
        self.assertEqual(body["date_time"]["filter_type"], 3)
        self.assertEqual(body["granularity"], 250)

    async def test_accepts_a_response_without_the_data_envelope(self):
        api = ScriptedFortyGuard(
            submit=(200, {"activity_id": ACTIVITY_ID}),
            statuses=[(200, {"status": "Completed", "result": HEATMAP_RESULT})],
        )
        client = self.build(api)

        activity_id, result = await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertEqual(activity_id, ACTIVITY_ID)
        self.assertEqual(result, HEATMAP_RESULT)


class TimeoutTests(FortyGuardClientTestCase):
    async def test_raises_after_fifteen_attempts_by_default(self):
        api = ScriptedFortyGuard(statuses=[STATUS_PROCESSING])
        client = self.build(api)

        with self.assertRaises(FortyGuardTimeout) as caught:
            await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertEqual(api.poll_count, 15)
        message = str(caught.exception)
        self.assertIn(ACTIVITY_ID, message)
        self.assertIn("15", message)
        self.assertIn("Completed", message)

    async def test_timeout_is_both_a_timeouterror_and_a_fortyguarderror(self):
        api = ScriptedFortyGuard(statuses=[STATUS_PROCESSING])
        client = self.build(api, poll_max_attempts=2)

        with self.assertRaises(FortyGuardTimeout) as caught:
            await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        # Callers can catch the builtin TimeoutError, or the module's base error.
        self.assertIsInstance(caught.exception, TimeoutError)
        self.assertIsInstance(caught.exception, FortyGuardError)

    async def test_respects_a_lower_configured_attempt_cap(self):
        api = ScriptedFortyGuard(statuses=[STATUS_PROCESSING])
        client = self.build(api, poll_max_attempts=3)

        with self.assertRaises(FortyGuardTimeout):
            await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertEqual(api.poll_count, 3)

    async def test_backoff_grows_exponentially_and_is_capped(self):
        api = ScriptedFortyGuard(statuses=[STATUS_PROCESSING])
        client = self.build(
            api,
            poll_max_attempts=6,
            poll_initial_delay_seconds=2.0,
            poll_backoff_factor=2.0,
            poll_max_delay_seconds=10.0,
        )

        with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
            with self.assertRaises(FortyGuardTimeout):
                await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        delays = [call.args[0] for call in sleep.await_args_list]
        self.assertEqual(delays, [2.0, 4.0, 8.0, 10.0, 10.0, 10.0])


class ApiErrorTests(FortyGuardClientTestCase):
    async def test_submit_server_error_raises(self):
        api = ScriptedFortyGuard(submit=(500, {"message": "boom"}))
        client = self.build(api)

        with self.assertRaises(FortyGuardError) as caught:
            await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertIn("HTTP 500", str(caught.exception))
        self.assertEqual(api.poll_count, 0, "must not poll when submit failed")

    async def test_submit_unauthorized_raises(self):
        api = ScriptedFortyGuard(submit=(401, {"message": "invalid api key"}))
        client = self.build(api)

        with self.assertRaises(FortyGuardError) as caught:
            await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertIn("HTTP 401", str(caught.exception))

    async def test_submit_without_activity_id_raises(self):
        api = ScriptedFortyGuard(submit=(200, {"data": {"queued": True}}))
        client = self.build(api)

        with self.assertRaises(FortyGuardError) as caught:
            await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertIn("no activity_id", str(caught.exception))

    async def test_submit_returning_a_json_list_raises(self):
        api = ScriptedFortyGuard(submit=(200, [1, 2, 3]))
        client = self.build(api)

        with self.assertRaises(FortyGuardError) as caught:
            await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertIn("expected a JSON object", str(caught.exception))

    async def test_status_server_error_raises(self):
        api = ScriptedFortyGuard(statuses=[(503, {"message": "unavailable"})])
        client = self.build(api)

        with self.assertRaises(FortyGuardError) as caught:
            await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertIn("HTTP 503", str(caught.exception))
        self.assertEqual(api.poll_count, 1, "a hard error must not be retried")

    async def test_failed_job_status_raises_without_exhausting_attempts(self):
        api = ScriptedFortyGuard(statuses=[STATUS_PROCESSING, (200, {"data": {"status": "Failed"}})])
        client = self.build(api)

        with self.assertRaises(FortyGuardError) as caught:
            await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertIn("failed", str(caught.exception))
        self.assertNotIsInstance(caught.exception, FortyGuardTimeout)
        self.assertEqual(api.poll_count, 2)

    async def test_completed_without_a_result_field_raises(self):
        api = ScriptedFortyGuard(statuses=[(200, {"data": {"status": "Completed"}})])
        client = self.build(api)

        with self.assertRaises(FortyGuardError) as caught:
            await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertIn("no 'result'", str(caught.exception))

    async def test_missing_api_key_raises_before_any_request(self):
        api = ScriptedFortyGuard()
        client = self.build(api, fortyguard_api_key="")

        with self.assertRaises(FortyGuardError) as caught:
            await client.fetch_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertIn("FORTYGUARD_API_KEY", str(caught.exception))
        self.assertEqual(api.heatmap_requests, [])


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_without_a_client_it_fails_loudly(self):
        client = FortyGuardClient(make_settings())

        with self.assertRaises(RuntimeError) as caught:
            await client.submit_heatmap(polygon_aoi=RING, date_time=WHEN)

        self.assertIn("async context manager", str(caught.exception))

    async def test_context_manager_creates_and_closes_its_own_client(self):
        # This is the one test that builds a real AsyncClient; setting up its SSL context
        # trips asyncio's debug-mode slow-callback warning, which is just noise here.
        asyncio.get_running_loop().slow_callback_duration = 5.0

        async with FortyGuardClient(make_settings()) as client:
            http = client._client
            self.assertFalse(http.is_closed)

        self.assertTrue(http.is_closed)

    async def test_an_injected_client_is_left_open_for_its_owner_to_close(self):
        http = httpx.AsyncClient(transport=httpx.MockTransport(ScriptedFortyGuard()))
        self.addAsyncCleanup(http.aclose)

        async with FortyGuardClient(make_settings(), http_client=http):
            pass

        self.assertFalse(http.is_closed)


if __name__ == "__main__":
    unittest.main()
