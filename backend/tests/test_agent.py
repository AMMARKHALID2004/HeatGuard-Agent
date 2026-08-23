"""Tests for `app.agent.HeatRiskAgent`.

An `httpx.MockTransport` is injected into a real `AsyncOpenAI` client, so the actual SDK
request/response path runs — serialization, auth header, envelope parsing — against scripted
replies. Nothing is stubbed and no network is touched.

    uv run python -m unittest discover -v
"""

import json
import unittest
from datetime import datetime
from typing import Any

import httpx
from openai import AsyncOpenAI

from app.agent import MAX_ATTEMPTS, AgentError, HeatRiskAgent
from app.config import Settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MODEL = "llama-3.3-70b-versatile"
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


class AgentTestCase(unittest.IsolatedAsyncioTestCase):
    def build(self, groq: ScriptedGroq, **setting_overrides: Any) -> HeatRiskAgent:
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
        # With no peak there is nothing to threshold, so the model's own call stands.
        self.assertEqual(decision.risk_level, "LOW")


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

    async def test_an_invented_temperature_is_nulled_when_nothing_was_measured(self):
        groq = ScriptedGroq(
            ok(decision_json(peak_temperature=34.5, average_temperature=33.1))
        )
        agent = self.build(groq)

        decision = await agent.assess(NO_READINGS, date_time=WHEN)

        self.assertIsNone(decision.peak_temperature)
        self.assertIsNone(decision.average_temperature)


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
