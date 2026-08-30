"""Tests for `POST /api/evaluate` — orchestration, alerting, and the error contract.

Two layers, on purpose:

- `EndToEndTests` drives the *whole* route over `httpx.MockTransport`: a real
  `FortyGuardClient` doing a real submit-and-poll, a real `AsyncOpenAI` client talking to a
  scripted Groq, real threshold enforcement, and a real Slack post. Nothing is patched, so
  it is the wiring itself under test.
- `OrchestrationTests` and `ErrorContractTests` patch one collaborator at a time to reach
  branches a scripted transport cannot reach cheaply — a poll budget running out, a
  malformed base URL, a rate limit.

    uv run python -m unittest discover -v
"""

import json
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from openai import AsyncOpenAI

from app.agent import (
    AgentError,
    AgentNotConfigured,
    AgentRateLimited,
    AgentTimeout,
    HeatRiskAgent,
)
from app.config import Settings, get_settings
from app.main import app
from app.risk import UNMEASURABLE_REASON as UNKNOWN_REASON
from app.schemas import AgentDecision
from app.services import slack
from app.services.fortyguard import (
    FortyGuardClient,
    FortyGuardError,
    FortyGuardNotConfigured,
    FortyGuardTimeout,
)

FORTYGUARD_BASE_URL = "https://api.fortyguard.com/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/T000/B000/xxxx"
ACTIVITY_ID = "act-42"

# One fixed construction site and work window, mirroring the demo scenario.
AOI = [[55.27, 25.20], [55.28, 25.20], [55.28, 25.21], [55.27, 25.21], [55.27, 25.20]]
REQUEST = {"polygon_aoi": AOI, "date_time": "2026-08-25T14:00:00"}

HOT = {"cells": [{"temperature": 41.2}, {"temperature": 38.4}]}   # peak 41.2 -> HIGH
MILD = {"cells": [{"temperature": 22.0}, {"temperature": 24.0}]}  # peak 24.0 -> LOW
NO_READINGS: dict[str, Any] = {"cells": []}                       # peak None -> MEDIUM floor
# Peak 35: HIGH under the default Mixed-Humid zone (>=33), but LOW in Hot-Dry (AZ, <36). The
# one heatmap whose verdict flips on the site's state — the whole point of the feature.
WARM_35 = {"cells": [{"temperature": 35.0}, {"temperature": 35.0}]}


def make_settings(**overrides: Any) -> Settings:
    """Route settings that ignore any real `.env`, so a developer's keys never leak in."""
    values: dict[str, Any] = {
        "fortyguard_api_key": "fg-test",
        "fortyguard_base_url": FORTYGUARD_BASE_URL,
        "groq_api_key": "gq-test",
        "groq_base_url": GROQ_BASE_URL,
        "groq_model": "openai/gpt-oss-120b",
        "slack_webhook_url": None,
        # The poll loop sleeps before every attempt; zero keeps the suite fast.
        "poll_initial_delay_seconds": 0.0,
        "poll_max_delay_seconds": 0.0,
        "poll_max_attempts": 3,
        "http_timeout_seconds": 5.0,
        "agent_deadline_seconds": 5.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def decision(**overrides: Any) -> AgentDecision:
    body: dict[str, Any] = {
        "risk_level": "HIGH",
        "peak_temperature": 41.2,
        "average_temperature": 39.8,
        "decision": "RESCHEDULE",
        "recommendation": "Move the pour to 06:00 and add a shaded break every 30 minutes.",
        "reason": "Peak of 41.2 C is at or above the 33 C HIGH threshold.",
    }
    body.update(overrides)
    return AgentDecision(**body)


def mild_decision() -> AgentDecision:
    """A coherent LOW verdict. Temperatures match the band, so no test enshrines a
    combination `enforce_thresholds` would never allow."""
    return decision(
        risk_level="LOW",
        decision="PROCEED",
        peak_temperature=24.0,
        average_temperature=23.0,
        recommendation="Normal hot-weather practice: water at each position, usual breaks.",
        reason="Peak of 24.0 C is below the 30 C MEDIUM threshold.",
    )


def medium_decision() -> AgentDecision:
    return decision(
        risk_level="MEDIUM",
        decision="MODIFY",
        peak_temperature=31.5,
        average_temperature=30.75,
        recommendation="Move the heaviest tasks earlier and add a shaded break each hour.",
        reason="Peak of 31.5 C falls in the 30-33 C MEDIUM band.",
    )


class RouteTestCase(unittest.TestCase):
    """A `TestClient` whose settings are overridden and cleaned up per test."""

    def client(self, **overrides: Any) -> TestClient:
        settings = make_settings(**overrides)
        app.dependency_overrides[get_settings] = lambda: settings
        self.addCleanup(app.dependency_overrides.clear)
        return TestClient(app)

    def post(self, client: TestClient, **body: Any) -> httpx.Response:
        return client.post("/api/evaluate", json={**REQUEST, **body})


# --------------------------------------------------------------------------------------
# Patch helpers. Async, because the real methods are.
# --------------------------------------------------------------------------------------


def fortyguard_returns(heatmap: Any, activity_id: str = ACTIVITY_ID) -> Any:
    async def fake(self: Any, **kwargs: Any) -> tuple[str, Any]:
        fake.calls.append(kwargs)  # type: ignore[attr-defined]
        return activity_id, heatmap

    fake.calls = []  # type: ignore[attr-defined]
    return patch.object(FortyGuardClient, "fetch_heatmap", fake), fake


def fortyguard_raises(exc: Exception) -> Any:
    async def fake(self: Any, **kwargs: Any) -> tuple[str, Any]:
        raise exc

    return patch.object(FortyGuardClient, "fetch_heatmap", fake)


def agent_returns(result: AgentDecision) -> Any:
    # `zone` is accepted (the router now passes it) but ignored: these fakes stand in for
    # the whole agent, so threshold enforcement isn't what's under test here.
    async def fake(
        self: Any, heatmap: Any, *, date_time: datetime, zone: Any = None
    ) -> AgentDecision:
        return result

    return patch.object(HeatRiskAgent, "assess", fake)


def agent_raises(exc: Exception) -> Any:
    async def fake(
        self: Any, heatmap: Any, *, date_time: datetime, zone: Any = None
    ) -> AgentDecision:
        raise exc

    return patch.object(HeatRiskAgent, "assess", fake)


def slack_records() -> Any:
    """Replace `slack.send_alert` with a recorder that reports success."""
    sent: list[AgentDecision] = []

    async def fake(settings: Settings, result: AgentDecision, **kw: Any) -> bool:
        sent.append(result)
        return True

    return patch.object(slack, "send_alert", fake), sent


# ======================================================================================


class EndToEndTests(RouteTestCase):
    """The real route, real clients, scripted transports. No patching of our own code."""

    def run_full_stack(
        self, heatmap: Any, *, slack_webhook_url: str | None = None, **request_overrides: Any
    ) -> tuple[httpx.Response, list[httpx.Request]]:
        """Drive the route with both upstreams scripted at the transport layer.

        `request_overrides` are merged into the POST body, so a caller can vary the request
        (e.g. `state="AZ"`) while keeping the same scripted heatmap.
        """
        seen: list[httpx.Request] = []
        # The model echoes the measured numbers back, as the prompt instructs.
        summary = {"cells": heatmap["cells"]}
        temps = [c["temperature"] for c in summary["cells"]]
        reply = {
            "risk_level": "HIGH" if temps and max(temps) >= 33 else "LOW",
            "peak_temperature": max(temps) if temps else None,
            "average_temperature": round(sum(temps) / len(temps), 2) if temps else None,
            "decision": "RESCHEDULE" if temps and max(temps) >= 33 else "PROCEED",
            "recommendation": "Start at 06:00 and rotate crews through shade every 30 minutes.",
            "reason": "Peak temperature relative to the fixed thresholds.",
        }

        def fortyguard_handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            if request.url.path.endswith("/heatmap"):
                return httpx.Response(200, json={"data": {"activity_id": ACTIVITY_ID}})
            return httpx.Response(
                200, json={"data": {"status": "Completed", "result": heatmap}}
            )

        def groq_handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-1",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "openai/gpt-oss-120b",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": json.dumps(reply)},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )

        def slack_handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, text="ok")

        real_fg_init = FortyGuardClient.__init__
        real_agent_aenter = HeatRiskAgent.__aenter__
        real_send_alert = slack.send_alert

        def patched_fg_init(self: Any, settings: Settings, **kw: Any) -> None:
            real_fg_init(
                self,
                settings,
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(fortyguard_handler)),
            )
            self._owns_http = True  # so __aexit__ still closes it

        async def patched_agent_aenter(self: Any) -> Any:
            self._openai = AsyncOpenAI(
                api_key="gq-test",
                base_url=GROQ_BASE_URL,
                max_retries=0,
                http_client=httpx.AsyncClient(transport=httpx.MockTransport(groq_handler)),
            )
            self._owns_client = True
            return self

        async def patched_send_alert(settings: Settings, result: Any, **kw: Any) -> bool:
            async with httpx.AsyncClient(transport=httpx.MockTransport(slack_handler)) as c:
                return await real_send_alert(settings, result, http_client=c)

        with (
            patch.object(FortyGuardClient, "__init__", patched_fg_init),
            patch.object(HeatRiskAgent, "__aenter__", patched_agent_aenter),
            patch.object(slack, "send_alert", patched_send_alert),
        ):
            client = self.client(slack_webhook_url=slack_webhook_url)
            return self.post(client, **request_overrides), seen

    def test_a_hot_site_reschedules_and_alerts_through_the_whole_stack(self):
        response, seen = self.run_full_stack(HOT, slack_webhook_url=SLACK_WEBHOOK_URL)

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["risk_level"], "HIGH")
        self.assertEqual(body["decision"], "RESCHEDULE")
        self.assertEqual(body["peak_temperature"], 41.2)
        self.assertEqual(body["average_temperature"], 39.8)
        self.assertEqual(body["activity_id"], ACTIVITY_ID)
        self.assertTrue(body["alert_sent"])

        # Submit, poll, Groq, Slack — the whole chain actually fired.
        paths = [r.url.path for r in seen]
        self.assertIn("/v1/heatmap", paths)
        self.assertIn(f"/v1/status/{ACTIVITY_ID}", paths)
        self.assertIn("/openai/v1/chat/completions", paths)
        self.assertTrue(any("hooks.slack.com" in str(r.url) for r in seen))

    def test_a_mild_site_proceeds_and_stays_silent(self):
        response, seen = self.run_full_stack(MILD, slack_webhook_url=SLACK_WEBHOOK_URL)

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["decision"], "PROCEED")
        self.assertFalse(body["alert_sent"])
        self.assertFalse(
            any("hooks.slack.com" in str(r.url) for r in seen),
            "PROCEED must never page anyone",
        )

    def test_the_api_key_reaches_fortyguard_but_never_the_response(self):
        response, seen = self.run_full_stack(HOT)

        submit = next(r for r in seen if r.url.path.endswith("/heatmap"))
        self.assertEqual(submit.headers["api-key"], "fg-test")
        # Nothing secret may come back out (CLAUDE.md → Secrets).
        self.assertNotIn("fg-test", response.text)
        self.assertNotIn("gq-test", response.text)

    def test_an_unreadable_heatmap_floors_to_caution_rather_than_clearing_the_shift(self):
        response, _ = self.run_full_stack(NO_READINGS)

        body = response.json()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(body["risk_level"], "MEDIUM")
        self.assertEqual(body["decision"], "MODIFY")
        self.assertIsNone(body["peak_temperature"])
        self.assertEqual(body["reason"], UNKNOWN_REASON)

    def test_the_same_peak_flips_verdict_on_the_sites_climate_zone(self):
        """35 C reschedules in the Northeast default but proceeds in Phoenix.

        Same heatmap, same measured peak, through the whole real stack — only the request's
        `state` changes. This is the feature's headline claim, proven end to end.
        """
        default_zone, seen_default = self.run_full_stack(WARM_35)
        self.assertEqual(default_zone.status_code, 200, default_zone.text)
        default_body = default_zone.json()
        self.assertEqual(default_body["peak_temperature"], 35.0)
        self.assertEqual(default_body["risk_level"], "HIGH")
        self.assertEqual(default_body["decision"], "RESCHEDULE")
        self.assertEqual(default_body["climate_zone"]["name"], "Mixed-Humid")
        self.assertEqual(default_body["climate_zone"]["medium_threshold_c"], 30.0)
        self.assertEqual(default_body["climate_zone"]["high_threshold_c"], 33.0)

        phoenix, _ = self.run_full_stack(WARM_35, state="AZ")
        self.assertEqual(phoenix.status_code, 200, phoenix.text)
        hot_dry_body = phoenix.json()
        # Same measured peak...
        self.assertEqual(hot_dry_body["peak_temperature"], 35.0)
        # ...different verdict, because Phoenix's crews are acclimatized to a higher cutoff.
        self.assertEqual(hot_dry_body["risk_level"], "LOW")
        self.assertEqual(hot_dry_body["decision"], "PROCEED")
        self.assertEqual(hot_dry_body["climate_zone"]["name"], "Hot-Dry")
        self.assertEqual(hot_dry_body["climate_zone"]["high_threshold_c"], 39.0)

    def test_the_resolved_zone_and_its_thresholds_come_back_in_the_response(self):
        """CLAUDE.md dashboards track: the card shows which zone's rules applied."""
        response, _ = self.run_full_stack(HOT, state="FL")

        zone = response.json()["climate_zone"]
        self.assertEqual(zone["name"], "Hot-Humid")
        self.assertEqual(zone["medium_threshold_c"], 34.0)
        self.assertEqual(zone["high_threshold_c"], 37.0)

    def test_an_unknown_state_falls_back_to_the_default_zone(self):
        """A state with no explicit entry (here NY) uses Mixed-Humid, unchanged behavior."""
        response, _ = self.run_full_stack(HOT, state="NY")

        self.assertEqual(response.json()["climate_zone"]["name"], "Mixed-Humid")


class OrchestrationTests(RouteTestCase):
    def test_the_request_parameters_reach_fortyguard(self):
        """CLAUDE.md → Known issue #1: the AOI and date must be real parameters."""
        fg, spy = fortyguard_returns(MILD)
        with fg, agent_returns(mild_decision()):
            response = self.post(
                self.client(), filter_type=2, granularity=250,
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(spy.calls), 1)
        call = spy.calls[0]
        self.assertEqual(call["polygon_aoi"], AOI)
        self.assertEqual(call["date_time"], datetime(2026, 8, 25, 14, 0))
        self.assertEqual(call["filter_type"], 2)
        self.assertEqual(call["granularity"], 250)

    def test_reschedule_alerts_and_reports_it(self):
        fg, _ = fortyguard_returns(HOT)
        alert, sent = slack_records()
        with fg, agent_returns(decision()), alert:
            response = self.post(self.client(slack_webhook_url=SLACK_WEBHOOK_URL))

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["alert_sent"])
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0].decision, "RESCHEDULE")

    def test_only_reschedule_alerts(self):
        for label, result in (("PROCEED", mild_decision()), ("MODIFY", medium_decision())):
            with self.subTest(decision=label):
                fg, _ = fortyguard_returns(MILD)
                alert, sent = slack_records()
                with fg, agent_returns(result), alert:
                    response = self.post(self.client(slack_webhook_url=SLACK_WEBHOOK_URL))

                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(sent, [])
                self.assertFalse(response.json()["alert_sent"])

    def test_a_broken_webhook_never_costs_the_decision(self):
        """The bug this pins: `httpx.InvalidURL` is not an `httpx.HTTPError`.

        A typo'd port in SLACK_WEBHOOK_URL used to escape `send_alert`'s handler and 500 the
        request, discarding a valid RESCHEDULE because a *notification* was misconfigured.
        The real `send_alert` runs here — only the URL is broken.
        """
        fg, _ = fortyguard_returns(HOT)
        with fg, agent_returns(decision()):
            response = self.post(
                self.client(slack_webhook_url="https://hooks.slack.com:notaport/services/x")
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["decision"], "RESCHEDULE")
        self.assertFalse(body["alert_sent"], "a failed post must report itself, not lie")

    def test_no_webhook_configured_is_not_a_failure(self):
        fg, _ = fortyguard_returns(HOT)
        with fg, agent_returns(decision()):
            response = self.post(self.client(slack_webhook_url=None))

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["alert_sent"])

    def test_the_response_carries_the_history_metadata_the_dashboard_needs(self):
        fg, _ = fortyguard_returns(HOT)
        with fg, agent_returns(decision()):
            response = self.post(self.client())

        body = response.json()
        self.assertEqual(body["activity_id"], ACTIVITY_ID)
        evaluated = datetime.fromisoformat(body["evaluated_at"])
        self.assertIsNotNone(evaluated.tzinfo, "evaluated_at must be timezone-aware")
        self.assertLess(
            abs((datetime.now(timezone.utc) - evaluated).total_seconds()), 30
        )
        self.assertEqual(
            set(body),
            {
                "risk_level", "peak_temperature", "average_temperature", "decision",
                "recommendation", "reason", "climate_zone", "activity_id",
                "evaluated_at", "alert_sent",
            },
        )


class ErrorContractTests(RouteTestCase):
    """Every failure maps to one status, one code, and a sentence worth showing a human."""

    # exception -> (status, code, retryable)
    CASES: dict[str, tuple[Exception, int, str, bool]] = {
        "poll budget exhausted": (
            FortyGuardTimeout("job act-42 did not reach 'Completed' after 15 status checks"),
            504, "fortyguard_timeout", True,
        ),
        "fortyguard rejected it": (
            FortyGuardError("heatmap submit failed with HTTP 401: bad key"),
            502, "fortyguard_failed", False,
        ),
        "fortyguard key missing": (
            FortyGuardNotConfigured("FORTYGUARD_API_KEY is not set"),
            500, "fortyguard_not_configured", False,
        ),
        "network read timeout": (
            httpx.ReadTimeout("timed out"), 504, "fortyguard_timeout", True,
        ),
        "connection refused": (
            httpx.ConnectError("refused"), 502, "fortyguard_unreachable", True,
        ),
        "malformed base url": (
            httpx.InvalidURL("bad port"), 500, "fortyguard_not_configured", False,
        ),
    }

    def test_each_fortyguard_failure_maps_to_its_own_status_and_code(self):
        for name, (exc, expected_status, code, retryable) in self.CASES.items():
            with self.subTest(failure=name):
                with fortyguard_raises(exc), agent_returns(decision()):
                    response = self.post(self.client())

                self.assertEqual(response.status_code, expected_status, response.text)
                body = response.json()
                self.assertEqual(body["error"]["code"], code)
                self.assertEqual(body["error"]["retryable"], retryable)

    def test_agent_failures_split_timeout_from_rate_limit_from_bad_output(self):
        cases = [
            (AgentTimeout("Groq did not produce a decision within 45s"), 504, "agent_timeout"),
            (AgentRateLimited("rate limited", retry_after_seconds=20.0), 503, "agent_rate_limited"),
            (AgentNotConfigured("GROQ_API_KEY is not set"), 500, "agent_not_configured"),
            (AgentError("Groq did not return a schema-valid decision in 2 attempts"),
             502, "agent_failed"),
        ]
        for exc, expected_status, code in cases:
            with self.subTest(failure=code):
                fg, _ = fortyguard_returns(HOT)
                with fg, agent_raises(exc):
                    response = self.post(self.client())

                self.assertEqual(response.status_code, expected_status, response.text)
                self.assertEqual(response.json()["error"]["code"], code)

    def test_a_rate_limit_passes_groqs_own_retry_after_through(self):
        fg, _ = fortyguard_returns(HOT)
        with fg, agent_raises(AgentRateLimited("slow down", retry_after_seconds=20.0)):
            response = self.post(self.client())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.headers["retry-after"], "20")
        self.assertIn("20 seconds", response.json()["detail"])

    def test_a_rate_limit_without_a_header_still_reads_sensibly(self):
        fg, _ = fortyguard_returns(HOT)
        with fg, agent_raises(AgentRateLimited("slow down")):
            response = self.post(self.client())

        self.assertEqual(response.status_code, 503)
        self.assertNotIn("retry-after", response.headers)
        self.assertIn("in a few seconds", response.json()["detail"])

    def test_every_error_body_has_the_same_shape(self):
        """Including 422, which FastAPI would otherwise return as a list of objects."""
        probes: list[tuple[str, httpx.Response]] = []

        with fortyguard_raises(FortyGuardTimeout("too slow")):
            probes.append(("504", self.post(self.client())))
        fg, _ = fortyguard_returns(HOT)
        with fg, agent_raises(AgentError("unusable")):
            probes.append(("502", self.post(self.client())))
        probes.append(("422", self.post(self.client(), polygon_aoi=[[0.0, 0.0]])))

        for label, response in probes:
            with self.subTest(status=label):
                body = response.json()
                self.assertIsInstance(body["detail"], str, "detail must be renderable text")
                self.assertEqual(body["detail"], body["error"]["message"])
                self.assertEqual(
                    set(body["error"]), {"code", "message", "hint", "retryable"}
                )
                self.assertTrue(body["error"]["message"].strip().endswith("."))

    def test_no_error_leaks_internals_to_the_browser(self):
        """The upstream's own text stays in the log. See `app.errors` for why."""
        leaky = FortyGuardError(
            "heatmap submit failed with HTTP 401: "
            '{"error":"invalid api-key fg-super-secret-value"}'
        )
        with fortyguard_raises(leaky):
            response = self.post(self.client())

        self.assertEqual(response.status_code, 502)
        self.assertNotIn("fg-super-secret-value", response.text)
        self.assertNotIn("401", response.text)
        # But it must still say something actionable.
        self.assertIn("FORTYGUARD_API_KEY", response.json()["error"]["hint"])

    def test_an_unexpected_exception_is_not_flattened_into_a_gateway_error(self):
        """`as_api_error` re-raises what it does not recognise, so bugs stay visible."""
        with fortyguard_raises(ZeroDivisionError("a real bug")):
            with self.assertRaises(ZeroDivisionError):
                self.post(self.client())


class RequestValidationTests(RouteTestCase):
    def test_a_malformed_aoi_is_rejected_with_a_readable_sentence(self):
        cases = {
            "too few vertices": [[55.27, 25.20], [55.28, 25.20]],
            "not a pair": [[55.27, 25.20, 3.0], [55.28, 25.20], [55.28, 25.21]],
            "longitude out of range": [[999.0, 25.20], [55.28, 25.20], [55.28, 25.21]],
            "latitude out of range": [[55.27, 91.0], [55.28, 25.20], [55.28, 25.21]],
        }
        for name, ring in cases.items():
            with self.subTest(aoi=name):
                response = self.post(self.client(), polygon_aoi=ring)

                self.assertEqual(response.status_code, 422, response.text)
                body = response.json()
                self.assertEqual(body["error"]["code"], "invalid_request")
                self.assertFalse(body["error"]["retryable"])
                self.assertIn("polygon_aoi", body["detail"])

    def test_a_missing_date_is_rejected(self):
        response = self.client().post("/api/evaluate", json={"polygon_aoi": AOI})

        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("date_time", response.json()["detail"])

    def test_a_valid_request_never_reaches_upstream_on_a_validation_failure(self):
        fg, spy = fortyguard_returns(HOT)
        with fg, agent_returns(decision()):
            self.post(self.client(), polygon_aoi=[[0.0, 0.0]])

        self.assertEqual(spy.calls, [], "a 422 must not burn a FortyGuard credit")


class SlackDeliveryTests(unittest.IsolatedAsyncioTestCase):
    """`send_alert` itself, over a scripted transport."""

    async def _send(self, handler: Any, **overrides: Any) -> tuple[bool, list[httpx.Request]]:
        seen: list[httpx.Request] = []

        def recording(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        settings = make_settings(slack_webhook_url=SLACK_WEBHOOK_URL, **overrides)
        async with httpx.AsyncClient(transport=httpx.MockTransport(recording)) as client:
            delivered = await slack.send_alert(settings, decision(), http_client=client)
        return delivered, seen

    async def test_a_delivered_alert_carries_the_verdict_and_the_guidance(self):
        delivered, seen = await self._send(lambda r: httpx.Response(200, text="ok"))

        self.assertTrue(delivered)
        self.assertEqual(len(seen), 1)
        body = json.loads(seen[0].content)
        self.assertIn("RESCHEDULE", body["text"])
        # Walk the blocks rather than the re-serialized string: `json.dumps` would escape
        # the degree sign back to ° and the assertion would test nothing.
        texts = [
            field["text"]
            for block in body["blocks"]
            for field in (block.get("fields") or [])
        ] + [
            block["text"]["text"] for block in body["blocks"] if isinstance(block.get("text"), dict)
        ] + [
            element["text"]
            for block in body["blocks"]
            for element in (block.get("elements") or [])
        ]
        self.assertTrue(any("41.2 °C" in t for t in texts), texts)
        self.assertTrue(any("39.8 °C" in t for t in texts), texts)
        self.assertTrue(any("shaded break" in t for t in texts), texts)

    async def test_slack_rejecting_the_post_is_reported_not_raised(self):
        delivered, _ = await self._send(lambda r: httpx.Response(403, text="invalid_token"))

        self.assertFalse(delivered)

    async def test_a_transport_failure_is_reported_not_raised(self):
        def boom(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route to host")

        delivered, _ = await self._send(boom)

        self.assertFalse(delivered)

    async def test_an_unset_webhook_skips_silently(self):
        settings = make_settings(slack_webhook_url=None)

        self.assertFalse(await slack.send_alert(settings, decision()))


if __name__ == "__main__":
    unittest.main()
