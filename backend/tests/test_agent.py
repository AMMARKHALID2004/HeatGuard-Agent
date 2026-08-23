"""Tests for `app.agent.HeatRiskAgent`.

An `httpx.MockTransport` is injected into a real `AsyncOpenAI` client, so the actual SDK
request/response path runs — serialization, auth header, envelope parsing — against scripted
replies. Nothing is stubbed and no network is touched.

    uv run python -m unittest discover -v
"""

import asyncio
import json
import unittest
from datetime import datetime
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.agent import MAX_ATTEMPTS, SDK_MAX_RETRIES, AgentError, HeatRiskAgent
from app.config import Settings
from app.risk import decision_for, reason_for, recommendation_for
from app.services.slack import _build_message  # the alert body itself is under test

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MODEL = "openai/gpt-oss-120b"
API_KEY = "test-key"
WHEN = datetime(2024, 7, 15, 14, 0)

# Heatmaps and the statistics `summarize_heatmap` derives from them.
HOT = {"cells": [{"temperature": 41.2}, {"temperature": 38.4}]}       # peak 41.2, avg 39.8
WARM = {"cells": [{"temperature": 31.5}, {"temperature": 30.0}]}      # peak 31.5, avg 30.75
MILD = {"cells": [{"temperature": 22.0}, {"temperature": 24.0}]}      # peak 24.0, avg 23.0
NO_READINGS: dict[str, Any] = {"cells": []}                          # peak None, avg None


def make_settings(**overrides: Any) -> Settings:
    """Test settings that ignore any real `.env`."""
    values: dict[str, Any] = {
        "groq_api_key": API_KEY,
        "groq_base_url": GROQ_BASE_URL,
        "groq_model": MODEL,
        "http_timeout_seconds": 5.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def decision_json(**overrides: Any) -> str:
    """A schema-valid agent reply, matching HOT unless overridden."""
    body: dict[str, Any] = {
        "risk_level": "HIGH",
        "peak_temperature": 41.2,
        "average_temperature": 39.8,
        "decision": "RESCHEDULE",
        "recommendation": "Move the pour to 06:00 and add a shaded break every 30 minutes.",
        "reason": "Peak of 41.2 C is at or above the 33 C HIGH threshold.",
    }
    body.update(overrides)
    return json.dumps(body)


def ok(content: str | None, *, finish_reason: str = "stop") -> tuple[int, Any]:
    """A 200 chat-completion envelope carrying `content`."""
    return 200, {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": MODEL,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }


class ScriptedGroq:
    """A `MockTransport` handler that scripts `/chat/completions` and records requests.

    Replies are consumed in order; the last one repeats, so a single entry stands in for
    "always fails this way".
    """

    def __init__(self, *replies: tuple[int, Any]):
        self.replies = list(replies) or [ok(decision_json())]
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.replies) - 1)
        code, payload = self.replies[index]
        return httpx.Response(code, json=payload)

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def body(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[index].content)

    def messages(self, index: int = 0) -> list[dict[str, str]]:
        return self.body(index)["messages"]


class SlowGroq:
    """A handler that stalls, so the reasoning deadline is what ends the call.

    `httpx.MockTransport` awaits an async handler, so this sleeps on the event loop rather
    than blocking it — `asyncio.timeout` can actually fire.
    """

    def __init__(self, *, delay: float):
        self.delay = delay
        self.requests: list[httpx.Request] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        await asyncio.sleep(self.delay)
        return httpx.Response(200, json=ok(decision_json())[1])

    @property
    def call_count(self) -> int:
        return len(self.requests)


class RawGroq:
    """A handler that returns a body verbatim, including bodies that are not JSON.

    `ScriptedGroq` serializes its replies, so it cannot express the 200s that matter here:
    a proxy's HTML error page, an empty body, or JSON that is not a chat completion.
    """

    def __init__(self, body: str | bytes, *, content_type: str = "application/json"):
        self.body = body.encode() if isinstance(body, str) else body
        self.content_type = content_type
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        # A fresh response each call: httpx marks a body as read once it is consumed.
        return httpx.Response(
            200, content=self.body, headers={"content-type": self.content_type}
        )

    @property
    def call_count(self) -> int:
        return len(self.requests)


class AgentTestCase(unittest.IsolatedAsyncioTestCase):
    def build(self, groq: Any, **setting_overrides: Any) -> HeatRiskAgent:
        http = httpx.AsyncClient(transport=httpx.MockTransport(groq))
        self.addAsyncCleanup(http.aclose)
        # max_retries=0 so the SDK's own transport retries cannot blur call counts; the
        # agent's single repair turn is the only retry under test.
        client = AsyncOpenAI(
            api_key=API_KEY, base_url=GROQ_BASE_URL, max_retries=0, http_client=http
        )
        return HeatRiskAgent(make_settings(**setting_overrides), client=client)


class RequestTests(AgentTestCase):
    async def test_calls_groq_with_the_configured_model_and_json_mode(self):
        groq = ScriptedGroq()
        agent = self.build(groq)

        await agent.assess(HOT, date_time=WHEN)

        request = groq.requests[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(str(request.url), f"{GROQ_BASE_URL}/chat/completions")
        self.assertEqual(request.headers["authorization"], f"Bearer {API_KEY}")

        body = groq.body()
        self.assertEqual(body["model"], MODEL)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["temperature"], 0.2)

    async def test_system_prompt_states_the_thresholds_and_the_mapping(self):
        groq = ScriptedGroq()
        agent = self.build(groq)

        await agent.assess(HOT, date_time=WHEN)

        system = groq.messages()[0]
        self.assertEqual(system["role"], "system")
        prompt = system["content"]
        for fragment in ("30 C", "33 C", "PROCEED", "MODIFY", "RESCHEDULE"):
            self.assertIn(fragment, prompt)
        # The never-invent rule must survive prompt edits.
        self.assertIn("null", prompt)
        self.assertRegex(prompt, r"[Nn]ever invent")

    async def test_user_prompt_carries_measured_stats_not_the_raw_grid(self):
        groq = ScriptedGroq()
        agent = self.build(groq)

        await agent.assess(HOT, date_time=WHEN)

        user = groq.messages()[1]
        self.assertEqual(user["role"], "user")
        payload = json.loads(user["content"])
        self.assertEqual(payload["peak_temperature_c"], 41.2)
        self.assertEqual(payload["average_temperature_c"], 39.8)
        self.assertEqual(payload["reading_count"], 2)
        self.assertEqual(payload["work_window_start"], WHEN.isoformat())
        # The grid itself never goes up.
        self.assertNotIn("cells", user["content"])


class SuccessTests(AgentTestCase):
    async def test_valid_reply_needs_a_single_call(self):
        groq = ScriptedGroq()
        agent = self.build(groq)

        decision = await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(groq.call_count, 1)
        self.assertEqual(decision.risk_level, "HIGH")
        self.assertEqual(decision.decision, "RESCHEDULE")
        self.assertEqual(decision.peak_temperature, 41.2)
        self.assertEqual(decision.average_temperature, 39.8)
        self.assertIn("06:00", decision.recommendation)

    async def test_missing_readings_stay_null(self):
        groq = ScriptedGroq(
            ok(
                decision_json(
                    risk_level="LOW",
                    decision="PROCEED",
                    peak_temperature=None,
                    average_temperature=None,
                    reason="No temperature readings were available for this area.",
                )
            )
        )
        agent = self.build(groq)

        decision = await agent.assess(NO_READINGS, date_time=WHEN)

        self.assertIsNone(decision.peak_temperature)
        self.assertIsNone(decision.average_temperature)
        # No measurement is not a clean bill of health: an unmeasurable area floors to
        # caution rather than inheriting the model's guess.
        self.assertEqual(decision.risk_level, "MEDIUM")
        self.assertEqual(decision.decision, "MODIFY")


class ThresholdEnforcementTests(AgentTestCase):
    async def test_a_hallucinated_low_on_a_hot_site_is_overridden(self):
        """The failure that actually matters: a wrong go-ahead at 41 C."""
        groq = ScriptedGroq(
            ok(decision_json(risk_level="LOW", decision="PROCEED"))
        )
        agent = self.build(groq)

        decision = await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(decision.risk_level, "HIGH")
        self.assertEqual(decision.decision, "RESCHEDULE")

    async def test_medium_band_maps_to_modify(self):
        groq = ScriptedGroq(
            ok(decision_json(risk_level="HIGH", decision="RESCHEDULE"))
        )
        agent = self.build(groq)

        decision = await agent.assess(WARM, date_time=WHEN)

        self.assertEqual(decision.peak_temperature, 31.5)
        self.assertEqual(decision.risk_level, "MEDIUM")
        self.assertEqual(decision.decision, "MODIFY")

    async def test_low_band_maps_to_proceed(self):
        groq = ScriptedGroq(
            ok(decision_json(risk_level="HIGH", decision="RESCHEDULE"))
        )
        agent = self.build(groq)

        decision = await agent.assess(MILD, date_time=WHEN)

        self.assertEqual(decision.peak_temperature, 24.0)
        self.assertEqual(decision.risk_level, "LOW")
        self.assertEqual(decision.decision, "PROCEED")

    async def test_an_edited_temperature_is_replaced_by_the_measurement(self):
        groq = ScriptedGroq(
            ok(decision_json(peak_temperature=12.0, average_temperature=11.0))
        )
        agent = self.build(groq)

        decision = await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(decision.peak_temperature, 41.2)
        self.assertEqual(decision.average_temperature, 39.8)
        self.assertEqual(decision.decision, "RESCHEDULE")

    async def test_a_corrected_temperature_takes_the_stale_reason_with_it(self):
        """Prose about the wrong number must not sit beside the corrected one."""
        groq = ScriptedGroq(
            ok(
                decision_json(
                    peak_temperature=12.0,
                    reason="Peak of 12.0 C is comfortably below the 30 C threshold.",
                )
            )
        )
        agent = self.build(groq)

        decision = await agent.assess(HOT, date_time=WHEN)

        self.assertNotIn("12.0", decision.reason)
        self.assertIn("41.2", decision.reason)

    async def test_a_faithful_reply_keeps_the_models_own_reason(self):
        """The model owns the prose; it is only overridden when it got a number wrong."""
        mine = "Peak of 41.2 C sits well above the 33 C cutoff for heavy outdoor work."
        groq = ScriptedGroq(ok(decision_json(reason=mine)))
        agent = self.build(groq)

        decision = await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(decision.reason, mine)

    async def test_an_invented_temperature_is_nulled_when_nothing_was_measured(self):
        groq = ScriptedGroq(
            ok(decision_json(peak_temperature=34.5, average_temperature=33.1))
        )
        agent = self.build(groq)

        decision = await agent.assess(NO_READINGS, date_time=WHEN)

        self.assertIsNone(decision.peak_temperature)
        self.assertIsNone(decision.average_temperature)


class ProseConsistencyTests(AgentTestCase):
    """Enforcing the verdict is only half the job: the words shown next to it must agree.

    `recommendation` and `reason` are printed verbatim on the dashboard card and inside the
    Slack alert. A reply that copied the temperatures faithfully but reasoned to the wrong
    band leaves `_reconcile` with nothing to correct, so without this the alert header says
    RESCHEDULE while the guidance underneath it says the opposite.
    """

    # Faithful temperatures, wrong verdict — the case that slips past every other guard.
    GO_AHEAD_AT_41C = {
        "risk_level": "LOW",
        "decision": "PROCEED",
        "recommendation": "Conditions are comfortable today. Run the full pour as "
                          "scheduled, no special heat precautions needed.",
        "reason": "Peak of 41.2 C is below the 30 C threshold, so risk is low.",
    }

    async def test_an_overridden_verdict_takes_the_models_prose_with_it(self):
        groq = ScriptedGroq(ok(decision_json(**self.GO_AHEAD_AT_41C)))
        agent = self.build(groq)

        decision = await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(decision.risk_level, "HIGH")
        self.assertEqual(decision.recommendation, recommendation_for("HIGH"))
        self.assertEqual(decision.reason, reason_for(41.2))
        self.assertNotIn("no special heat precautions", decision.recommendation)
        self.assertNotIn("below", decision.reason)

    async def test_a_faithful_reply_keeps_the_models_own_recommendation(self):
        """The model's prose is the point of having one — it is only dropped when wrong."""
        mine = "Start at 05:30, rotate crews every 20 minutes, and park the ice chest on deck."
        groq = ScriptedGroq(ok(decision_json(recommendation=mine)))
        agent = self.build(groq)

        decision = await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(decision.recommendation, mine)

    async def test_the_slack_alert_never_contradicts_its_own_headline(self):
        """The alert is the one surface a supervisor reads without opening the dashboard."""
        groq = ScriptedGroq(ok(decision_json(**self.GO_AHEAD_AT_41C)))
        agent = self.build(groq)

        decision = await agent.assess(HOT, date_time=WHEN)
        body = json.dumps(_build_message(decision))

        self.assertIn("RESCHEDULE", body)
        self.assertNotIn("no special heat precautions", body)
        self.assertNotIn("risk is low", body)

    async def test_whichever_band_the_model_misses_the_guidance_matches_the_verdict(self):
        for heatmap, expected in ((HOT, "HIGH"), (WARM, "MEDIUM"), (MILD, "LOW")):
            with self.subTest(expected=expected):
                # Always claim the band the thresholds will not reach.
                wrong = "LOW" if expected != "LOW" else "HIGH"
                groq = ScriptedGroq(
                    ok(decision_json(risk_level=wrong, decision=decision_for(wrong)))
                )
                agent = self.build(groq)

                decision = await agent.assess(heatmap, date_time=WHEN)

                self.assertEqual(decision.risk_level, expected)
                self.assertEqual(decision.recommendation, recommendation_for(expected))


class UnmeasurableAreaTests(AgentTestCase):
    """A heatmap the parser cannot read must never produce a go-ahead.

    `services/heatmap.py` carries a TODO(fortyguard-docs): the real result schema is
    unconfirmed, so "zero readings found" is a live risk, not a hypothetical. Whatever the
    model says on that path, the answer is decided in code.
    """

    async def test_no_readings_never_yields_proceed_whatever_the_model_says(self):
        for risk_level, decision_value in (
            ("LOW", "PROCEED"),
            ("MEDIUM", "MODIFY"),
            ("HIGH", "RESCHEDULE"),
        ):
            with self.subTest(model_said=f"{risk_level}/{decision_value}"):
                groq = ScriptedGroq(
                    ok(
                        decision_json(
                            risk_level=risk_level,
                            decision=decision_value,
                            peak_temperature=None,
                            average_temperature=None,
                        )
                    )
                )
                agent = self.build(groq)

                result = await agent.assess(NO_READINGS, date_time=WHEN)

                self.assertEqual(result.decision, "MODIFY")
                self.assertEqual(result.risk_level, "MEDIUM")
                self.assertNotEqual(result.decision, "PROCEED")

    async def test_no_readings_never_fires_a_slack_alert_off_a_guess(self):
        """RESCHEDULE is the Slack trigger, so a hallucinated HIGH must not reach it."""
        groq = ScriptedGroq(
            ok(decision_json(risk_level="HIGH", decision="RESCHEDULE"))
        )
        agent = self.build(groq)

        result = await agent.assess(NO_READINGS, date_time=WHEN)

        self.assertNotEqual(result.decision, "RESCHEDULE")

    async def test_the_reason_explains_the_missing_data_not_a_dropped_temperature(self):
        groq = ScriptedGroq(
            ok(decision_json(reason="Peak of 41.2 C is above the 33 C HIGH threshold."))
        )
        agent = self.build(groq)

        result = await agent.assess(NO_READINGS, date_time=WHEN)

        # The model's reason described a temperature that got nulled; it must not survive
        # next to a blank peak on the card.
        self.assertNotIn("41.2", result.reason)
        self.assertIn("no usable temperature readings", result.reason.lower())

    async def test_risk_level_and_decision_never_contradict_each_other(self):
        """A mismatched pair must be repaired, not passed through."""
        for heatmap in (HOT, WARM, MILD, NO_READINGS):
            with self.subTest(heatmap=heatmap):
                groq = ScriptedGroq(
                    ok(decision_json(risk_level="HIGH", decision="PROCEED"))
                )
                agent = self.build(groq)

                result = await agent.assess(heatmap, date_time=WHEN)

                expected = {"LOW": "PROCEED", "MEDIUM": "MODIFY", "HIGH": "RESCHEDULE"}
                self.assertEqual(result.decision, expected[result.risk_level])


class RetryTests(AgentTestCase):
    async def test_malformed_json_is_retried_once_and_then_succeeds(self):
        groq = ScriptedGroq(ok("not json at all"), ok(decision_json()))
        agent = self.build(groq)

        decision = await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(groq.call_count, 2)
        self.assertEqual(decision.decision, "RESCHEDULE")

    async def test_a_schema_violation_is_retried(self):
        groq = ScriptedGroq(
            ok(json.dumps({"risk_level": "SCORCHING", "decision": "PANIC"})),
            ok(decision_json()),
        )
        agent = self.build(groq)

        decision = await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(groq.call_count, 2)
        self.assertEqual(decision.risk_level, "HIGH")

    async def test_an_empty_reply_is_retried(self):
        groq = ScriptedGroq(ok(None), ok(decision_json()))
        agent = self.build(groq)

        decision = await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(groq.call_count, 2)
        self.assertEqual(decision.decision, "RESCHEDULE")

    async def test_the_repair_turn_replays_the_reply_and_quotes_the_problem(self):
        groq = ScriptedGroq(
            ok(json.dumps({"risk_level": "HIGH"})),  # missing four required keys
            ok(decision_json()),
        )
        agent = self.build(groq)

        await agent.assess(HOT, date_time=WHEN)

        retry_messages = groq.messages(1)
        # Original system + user, then the rejected reply, then the correction.
        self.assertEqual(len(retry_messages), 4)
        self.assertEqual([m["role"] for m in retry_messages],
                         ["system", "user", "assistant", "user"])
        self.assertEqual(retry_messages[2]["content"], json.dumps({"risk_level": "HIGH"}))
        correction = retry_messages[3]["content"]
        self.assertIn("rejected", correction)
        # The specific validation failure is fed back, not just a generic scolding.
        self.assertIn("decision", correction)
        self.assertIn("recommendation", correction)

    async def test_two_invalid_replies_raise_a_clear_error(self):
        groq = ScriptedGroq(ok("still not json"))
        agent = self.build(groq)

        with self.assertRaises(AgentError) as caught:
            await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(groq.call_count, MAX_ATTEMPTS)
        self.assertEqual(groq.call_count, 2)
        message = str(caught.exception)
        self.assertIn("2 attempts", message)
        self.assertIn(MODEL, message)
        # The error says why it was rejected, not just that it was.
        self.assertRegex(message, r"[Ll]ast rejection")

    async def test_it_never_makes_a_third_attempt(self):
        groq = ScriptedGroq(ok("{"), ok("{"), ok(decision_json()))
        agent = self.build(groq)

        with self.assertRaises(AgentError):
            await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(groq.call_count, 2, "a valid third reply must never be reached")


class ApiErrorTests(AgentTestCase):
    async def test_server_error_raises_without_a_repair_turn(self):
        groq = ScriptedGroq((500, {"error": {"message": "internal"}}))
        agent = self.build(groq)

        with self.assertRaises(AgentError) as caught:
            await agent.assess(HOT, date_time=WHEN)

        self.assertIn("500", str(caught.exception))
        self.assertEqual(groq.call_count, 1, "an API failure is not a schema failure")

    async def test_rate_limit_raises(self):
        groq = ScriptedGroq((429, {"error": {"message": "rate limit reached"}}))
        agent = self.build(groq)

        with self.assertRaises(AgentError) as caught:
            await agent.assess(HOT, date_time=WHEN)

        self.assertIn("429", str(caught.exception))

    async def test_unauthorized_raises(self):
        groq = ScriptedGroq((401, {"error": {"message": "invalid api key"}}))
        agent = self.build(groq)

        with self.assertRaises(AgentError) as caught:
            await agent.assess(HOT, date_time=WHEN)

        self.assertIn("401", str(caught.exception))

    async def test_a_reply_with_no_choices_is_retried_then_raises(self):
        groq = ScriptedGroq((200, {
            "id": "c", "object": "chat.completion", "created": 0,
            "model": MODEL, "choices": [],
        }))
        agent = self.build(groq)

        with self.assertRaises(AgentError):
            await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(groq.call_count, 2)


class MalformedEnvelopeTests(AgentTestCase):
    """A 200 that is not a chat completion must still come out as `AgentError` -> 502.

    The SDK builds its response models without validating them, so these arrive as a plain
    string or an object with fields missing rather than as an exception. `evaluate.py` only
    catches `AgentError`, so anything else here is an unhandled 500 traceback at the one
    moment the dashboard is on screen. The realistic trigger is a mistyped `GROQ_BASE_URL`
    or a captive proxy answering 200 with its own page.
    """

    CASES = {
        "html error page": ("<html><body>502 Bad Gateway</body></html>", "text/html"),
        "plain text": ("Service Unavailable", "text/plain"),
        "empty body": ("", "application/json"),
        "json, but not an envelope": ('{"error": "rate limited"}', "application/json"),
        "envelope with null choices": (
            '{"id": "c", "object": "chat.completion", "created": 0, "choices": null}',
            "application/json",
        ),
    }

    async def test_a_200_that_is_not_a_chat_completion_raises_agent_error(self):
        for label, (body, content_type) in self.CASES.items():
            with self.subTest(reply=label):
                agent = self.build(RawGroq(body, content_type=content_type))

                with self.assertRaises(AgentError):
                    await agent.assess(HOT, date_time=WHEN)

    async def test_the_error_says_where_to_look(self):
        agent = self.build(RawGroq("<html>nope</html>", content_type="text/html"))

        with self.assertRaises(AgentError) as caught:
            await agent.assess(HOT, date_time=WHEN)

        self.assertIn("GROQ_BASE_URL", str(caught.exception))

    async def test_a_non_envelope_earns_no_repair_turn(self):
        """A body the model never wrote will not be fixed by asking the model again."""
        groq = RawGroq('{"error": "rate limited"}')
        agent = self.build(groq)

        with self.assertRaises(AgentError):
            await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(groq.call_count, 1)


class DeadlineTests(AgentTestCase):
    """The reasoning phase is capped in wall-clock, not just per request.

    A per-request timeout is not enough: `MAX_ATTEMPTS` multiplies it, and the SDK honours a
    server `Retry-After` that can dwarf the request itself. On Groq's free tier that is how
    a dashboard button ends up spinning past the demo window.
    """

    async def test_a_slow_groq_is_cut_off_at_the_deadline(self):
        groq = SlowGroq(delay=5.0)
        agent = self.build(groq, agent_deadline_seconds=0.15)

        with self.assertRaises(AgentError) as caught:
            await agent.assess(HOT, date_time=WHEN)

        message = str(caught.exception)
        self.assertIn("0.15s", message)
        self.assertIn(MODEL, message)

    async def test_the_deadline_error_is_an_agent_error_the_router_already_maps(self):
        """`evaluate.py` catches `AgentError` -> 502; a bare TimeoutError would be a 500."""
        groq = SlowGroq(delay=5.0)
        agent = self.build(groq, agent_deadline_seconds=0.15)

        with self.assertRaises(AgentError):
            await agent.assess(HOT, date_time=WHEN)

    async def test_a_prompt_reply_is_untouched_by_the_deadline(self):
        groq = ScriptedGroq()
        agent = self.build(groq, agent_deadline_seconds=30.0)

        decision = await agent.assess(HOT, date_time=WHEN)

        self.assertEqual(decision.decision, "RESCHEDULE")

    async def test_sdk_retries_are_bounded_so_one_click_cannot_fan_out(self):
        """With the real `SDK_MAX_RETRIES`, a persistent 500 costs 1 + retries requests."""
        groq = ScriptedGroq((500, {"error": {"message": "internal"}}))
        http = httpx.AsyncClient(transport=httpx.MockTransport(groq))
        self.addAsyncCleanup(http.aclose)
        client = AsyncOpenAI(
            api_key=API_KEY,
            base_url=GROQ_BASE_URL,
            max_retries=SDK_MAX_RETRIES,
            http_client=http,
        )
        agent = HeatRiskAgent(make_settings(), client=client)

        with self.assertRaises(AgentError):
            await agent.assess(HOT, date_time=WHEN)

        # An API error never earns a repair turn, so this is the whole cost of one click.
        self.assertEqual(groq.call_count, 1 + SDK_MAX_RETRIES)
        self.assertLessEqual(groq.call_count, 2, "retry amplification must stay small")


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_api_key_raises_on_entry(self):
        with self.assertRaises(AgentError) as caught:
            async with HeatRiskAgent(make_settings(groq_api_key="")):
                pass

        self.assertIn("GROQ_API_KEY", str(caught.exception))

    async def test_without_a_client_it_fails_loudly(self):
        agent = HeatRiskAgent(make_settings())

        with self.assertRaises(RuntimeError) as caught:
            await agent.assess(HOT, date_time=WHEN)

        self.assertIn("async context manager", str(caught.exception))

    async def test_context_manager_builds_a_client_against_the_groq_endpoint(self):
        async with HeatRiskAgent(make_settings()) as agent:
            client = agent._client
            self.assertEqual(str(client.base_url).rstrip("/"), GROQ_BASE_URL)
            self.assertEqual(client.api_key, API_KEY)

        self.assertIsNone(agent._openai, "it should release the client it created")

    async def test_an_injected_client_is_left_open_for_its_owner_to_close(self):
        http = httpx.AsyncClient(transport=httpx.MockTransport(ScriptedGroq()))
        self.addAsyncCleanup(http.aclose)
        client = AsyncOpenAI(api_key=API_KEY, base_url=GROQ_BASE_URL, http_client=http)

        async with HeatRiskAgent(make_settings(), client=client):
            pass

        self.assertFalse(http.is_closed)


if __name__ == "__main__":
    unittest.main()
