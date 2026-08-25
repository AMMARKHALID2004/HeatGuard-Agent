"""HeatRiskAgent — turns a FortyGuard heatmap into a go/no-go decision for a work shift.

Reasoning runs on Groq's OpenAI-compatible endpoint through the official `openai` SDK: an
`AsyncOpenAI` client pointed at `settings.groq_base_url` and authenticated with
`GROQ_API_KEY`. The reply is validated against `AgentDecision`.

Two things are guaranteed in code rather than trusted to the prompt, because a confident
go-ahead on a 41 °C site is the one failure mode that actually matters:

- **The numbers are measured, not generated.** `peak_temperature` and
  `average_temperature` are overwritten with what `summarize_heatmap` computed from the
  FortyGuard grid. When the heatmap carried no readings they stay `null`, so a model that
  helpfully invents "34.5" cannot get it onto the dashboard.
- **The classification is thresholded, not reasoned.** `risk_level` and `decision` are
  re-derived by `app.risk.enforce_thresholds` from that measured peak
  (CLAUDE.md → "do not let the LLM decide thresholds itself"). That holds on the
  no-reading path too, where the peak is `null`: rather than leave the verdict to the
  model, an unmeasurable area floors to MEDIUM/MODIFY. A green PROCEED is a safety claim,
  and an unparsed heatmap cannot back one.

That leaves the model responsible for exactly what it is good at: the plain-language
`recommendation` and `reason`. Those are kept verbatim only while they still describe the
verdict that shipped — when a threshold override contradicts what the model argued for, its
prose is replaced along with its verdict, because the dashboard card and the Slack alert
print both side by side.

A reply that is not valid JSON, or does not fit `AgentDecision`, is handed back once as a
repair turn quoting the validation error. A second failure raises `AgentError`. The whole
phase — both attempts and every SDK backoff sleep inside them — is capped by
`settings.agent_deadline_seconds`, so a rate-limited free tier cannot outlast the demo.
"""

import asyncio
import json
import logging
from datetime import datetime
from types import TracebackType
from typing import Any, Self

from openai import APIStatusError, AsyncOpenAI, OpenAIError, RateLimitError
from pydantic import ValidationError

from .climate import DEFAULT_ZONE, ClimateZone
from .config import Settings
from .risk import enforce_thresholds, reason_for
from .schemas import AgentDecision
from .services.heatmap import summarize_heatmap

logger = logging.getLogger(__name__)

# One initial call plus one repair turn. This counts *schema* attempts.
MAX_ATTEMPTS = 2

# Transport-level retries the SDK performs itself for transient 429s and 5xx. Kept at one,
# not the SDK's default of two: it multiplies with MAX_ATTEMPTS, so each extra retry costs
# two more requests per button press and makes the free-tier 429 it exists to absorb more
# likely. The SDK honours a server `Retry-After` of up to 120s per retry, which is why
# `settings.agent_deadline_seconds` caps the phase regardless of what this is set to.
# Orthogonal to MAX_ATTEMPTS: a 200 carrying malformed JSON is not a transport failure.
SDK_MAX_RETRIES = 1

# Low but non-zero: the decision is deterministic, only the prose should vary.
SAMPLING_TEMPERATURE = 0.2

# How much of an offending reply to put in the log.
_LOG_EXCERPT = 400


class AgentError(RuntimeError):
    """Groq was unreachable, misconfigured, or never produced a usable decision."""


class AgentNotConfigured(AgentError):
    """No `GROQ_API_KEY`. An operator problem, not an upstream one — retrying cannot help."""


class AgentTimeout(AgentError, TimeoutError):
    """The reasoning phase outlasted `settings.agent_deadline_seconds`.

    Subclasses the builtin `TimeoutError` too, matching `FortyGuardTimeout`, so a caller can
    catch either the agent's failures or every timeout in the request.
    """


class AgentRateLimited(AgentError):
    """Groq returned 429. Distinct because it is the one failure with a *when* attached.

    `retry_after_seconds` is Groq's own `Retry-After` when it sent one, so the API can pass a
    real number to the dashboard rather than an unqualified "try again later".
    """

    def __init__(self, message: str, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class _UnusableReply(Exception):
    """Internal: this reply cannot become an `AgentDecision`, so it earns a repair turn."""


def build_system_prompt(zone: ClimateZone) -> str:
    """The system prompt for one site's climate zone.

    Per-request, not an import-time constant: the LOW/MEDIUM/HIGH cutoffs and the zone name
    are the site's, because a peak that is safe in one region is dangerous in another. Every
    other rule (never invent a temperature, null when unavailable, the LOW->PROCEED /
    MEDIUM->MODIFY / HIGH->RESCHEDULE mapping, JSON-only) is fixed. The model still never
    chooses the thresholds — `app.risk.enforce_thresholds` re-derives the verdict from these
    same numbers; the prompt only mirrors them so the model's prose stays consistent.
    """
    medium = zone.medium_threshold_c
    high = zone.high_threshold_c
    return f"""\
You are HeatGuard, a heat-safety agent for outdoor construction crews. You are given
temperature statistics for one work area and one work window, and you return a go/no-go
decision for that shift.

This site is in the {zone.name} US climate zone. Safe-work temperatures are regional —
crews acclimatized to a hotter zone tolerate a higher peak — so classify on PEAK
temperature in Celsius against THIS zone's thresholds. They are fixed for this request —
never adjust them, reinterpret them, or substitute your own judgement:

  risk_level   peak temperature                  decision
  LOW          peak < {medium:g} C                        PROCEED
  MEDIUM       {medium:g} C <= peak < {high:g} C              MODIFY
  HIGH         peak >= {high:g} C                       RESCHEDULE

Never invent, estimate, extrapolate, or fill in a temperature. Use only the numbers you
were given. If a temperature was not provided, return null for it and say it was
unavailable in `reason`. A null is always better than a guess.

If no temperature was provided at all, write `recommendation` for a site that could not be
measured: assume caution, and tell the supervisor to verify conditions on the ground before
committing the crew. Do not clear the shift on missing data.

Write `recommendation` as one or two sentences of concrete guidance a site supervisor can
act on today: shift timing, hydration and rest cadence, shade, task swaps. No hedging.
Write `reason` as one sentence naming the peak temperature and the threshold it crossed;
you may name the {zone.name} zone to explain why this cutoff applies.

Reply with a single JSON object and nothing else — no prose, no markdown fences — with
exactly these six keys:

{{"risk_level": "LOW" | "MEDIUM" | "HIGH",
  "peak_temperature": number | null,
  "average_temperature": number | null,
  "decision": "PROCEED" | "MODIFY" | "RESCHEDULE",
  "recommendation": "...",
  "reason": "..."}}
"""

_REPAIR_INSTRUCTION = (
    "That reply was rejected: {problem}.\n"
    "Return only the JSON object, with exactly the six required keys and the allowed enum "
    "values. No prose, no markdown fences, no extra keys. Keep the temperatures exactly as "
    "they were given to you, or null where they were unavailable."
)


def build_user_prompt(
    summary: dict[str, Any], date_time: datetime, zone: ClimateZone = DEFAULT_ZONE
) -> str:
    """Hand the model the measured statistics — never the raw grid."""
    return json.dumps(
        {
            "work_window_start": date_time.isoformat(),
            "climate_zone": zone.name,
            "peak_temperature_c": summary["peak_temperature"],
            "average_temperature_c": summary["average_temperature"],
            "reading_count": summary["reading_count"],
            "sample_temperatures_c": summary["sample"],
        },
        indent=2,
    )


def _describe(exc: ValidationError) -> str:
    """Flatten a `ValidationError` into something worth showing the model."""
    problems = []
    for error in exc.errors()[:6]:
        location = ".".join(str(part) for part in error["loc"]) or "(root)"
        problems.append(f"{location}: {error['msg']}")
    return "; ".join(problems) or str(exc)


def _parse(content: str) -> AgentDecision:
    """Validate a raw reply, or raise `_UnusableReply` describing why it failed.

    `model_validate_json` reports malformed JSON and schema violations through the same
    `ValidationError`, so both arrive here on one path.
    """
    if not content.strip():
        raise _UnusableReply("the reply was empty")
    try:
        return AgentDecision.model_validate_json(content)
    except ValidationError as exc:
        raise _UnusableReply(_describe(exc)) from exc


def _reconcile(
    decision: AgentDecision, summary: dict[str, Any], zone: ClimateZone = DEFAULT_ZONE
) -> AgentDecision:
    """Replace the model's temperatures with the measured ones, then re-apply thresholds.

    A mismatch means the model edited a number it was told to copy. That is logged and
    corrected rather than raised: the measured value is already known, so failing the whole
    request would throw away a good answer over the model's arithmetic.
    """
    updates: dict[str, Any] = {}
    for field, measured in (
        ("peak_temperature", summary["peak_temperature"]),
        ("average_temperature", summary["average_temperature"]),
    ):
        if getattr(decision, field) != measured:
            logger.warning(
                "Model reported %s=%s but the heatmap measured %s — using the measurement",
                field,
                getattr(decision, field),
                measured,
            )
            updates[field] = measured

    if updates:
        # The model's `reason` narrates a temperature it just got wrong, so it would
        # contradict the corrected number on the same card. Restate it from the
        # measurement. (`enforce_thresholds` replaces this again if the peak is null.)
        peak = summary["peak_temperature"]
        if peak is not None:
            updates["reason"] = reason_for(peak, zone)
        decision = decision.model_copy(update=updates)
    return enforce_thresholds(decision, zone)


def _reply_content(completion: Any) -> str | None:
    """The reply text out of a chat-completion envelope, or `None` if it is not one.

    The SDK builds its response models without validating them, so a 200 that is not a chat
    completion — a proxy's JSON error page, or whatever sits at a mistyped `GROQ_BASE_URL` —
    arrives here as a plain string or an object with fields missing, rather than as an
    exception. Returning `None` lets the caller name that specifically, instead of the
    request dying on an `AttributeError` the router does not catch.
    """
    choices = getattr(completion, "choices", None)
    if choices is None:
        return None
    if not choices:
        # A real envelope that simply carried nothing. Distinct from the case above, and
        # worth the one repair turn.
        logger.warning("Groq returned no choices")
        return ""
    try:
        choice = choices[0]
        if choice.finish_reason == "length":
            logger.warning("Groq reply hit the token limit and is probably truncated")
        return choice.message.content or ""
    except (AttributeError, TypeError, KeyError, IndexError):
        return None


def _retry_after_seconds(exc: APIStatusError) -> float | None:
    """Groq's `Retry-After`, in seconds, or `None` if it did not send a usable one.

    Sent as an integer count of seconds in practice, but the header is also allowed to be an
    HTTP-date, and Groq has been known to append a unit ("2s"). Anything unparseable becomes
    `None` so the API says "in a few seconds" rather than inventing a number.
    """
    response = getattr(exc, "response", None)
    raw = getattr(response, "headers", {}).get("retry-after") if response else None
    if not raw:
        return None
    try:
        return float(str(raw).strip().rstrip("s"))
    except ValueError:
        return None


class HeatRiskAgent:
    """Reason about one heatmap and return a validated `AgentDecision`.

    Owns its `AsyncOpenAI` client when used as an async context manager:

        async with HeatRiskAgent(settings) as agent:
            decision = await agent.assess(heatmap, date_time=when)

    Pass `client` to inject one instead — that is how the tests drive the real SDK over an
    `httpx.MockTransport`.
    """

    def __init__(self, settings: Settings, *, client: AsyncOpenAI | None = None):
        self._settings = settings
        self._openai = client
        self._owns_client = client is None

    async def __aenter__(self) -> Self:
        if self._openai is None:
            self._openai = self._build_client()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._owns_client and self._openai is not None:
            await self._openai.close()
            self._openai = None

    def _build_client(self) -> AsyncOpenAI:
        if not self._settings.groq_api_key:
            raise AgentNotConfigured("GROQ_API_KEY is not set")
        return AsyncOpenAI(
            api_key=self._settings.groq_api_key,
            base_url=self._settings.groq_base_url,
            timeout=self._settings.http_timeout_seconds,
            max_retries=SDK_MAX_RETRIES,
        )

    @property
    def _client(self) -> AsyncOpenAI:
        if self._openai is None:
            raise RuntimeError(
                "HeatRiskAgent has no LLM client: use it as an async context manager, "
                "or pass client="
            )
        return self._openai

    async def assess(
        self, heatmap: Any, *, date_time: datetime, zone: ClimateZone = DEFAULT_ZONE
    ) -> AgentDecision:
        """Summarize `heatmap`, reason about it, and return a validated decision.

        `zone` supplies the site's thresholds, so the same measured peak can classify
        differently depending on where the work is. Raises `AgentError` if Groq is
        unreachable or misconfigured, if it fails to produce a schema-valid decision within
        `MAX_ATTEMPTS`, or if the whole phase outlasts `settings.agent_deadline_seconds`.
        """
        summary = summarize_heatmap(heatmap)
        logger.info(
            "Assessing heatmap (zone=%s): readings=%s peak=%s average=%s",
            zone.name,
            summary["reading_count"],
            summary["peak_temperature"],
            summary["average_temperature"],
        )

        deadline = self._settings.agent_deadline_seconds
        try:
            # One ceiling over every attempt, including the SDK's own backoff sleeps. A
            # per-request timeout is not enough: retries multiply it, and a free-tier
            # `Retry-After` can be far longer than the request itself.
            async with asyncio.timeout(deadline):
                return await self._reason(summary, date_time, zone)
        except TimeoutError as exc:
            raise AgentTimeout(
                f"Groq did not produce a decision within {deadline:g}s "
                f"(model={self._settings.groq_model})"
            ) from exc

    async def _reason(
        self, summary: dict[str, Any], date_time: datetime, zone: ClimateZone = DEFAULT_ZONE
    ) -> AgentDecision:
        """The attempt loop: one call, then at most one repair turn."""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": build_system_prompt(zone)},
            {"role": "user", "content": build_user_prompt(summary, date_time, zone)},
        ]

        problem = ""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            content = await self._complete(messages)
            try:
                decision = _parse(content)
            except _UnusableReply as exc:
                problem = str(exc)
                logger.warning(
                    "Groq reply rejected (attempt %s/%s): %s | raw=%.*s",
                    attempt,
                    MAX_ATTEMPTS,
                    problem,
                    _LOG_EXCERPT,
                    content,
                )
                if attempt < MAX_ATTEMPTS:
                    messages += [
                        {"role": "assistant", "content": content or "(empty reply)"},
                        {
                            "role": "user",
                            "content": _REPAIR_INSTRUCTION.format(problem=problem),
                        },
                    ]
                continue

            return _reconcile(decision, summary, zone)

        raise AgentError(
            f"Groq did not return a schema-valid decision in {MAX_ATTEMPTS} attempts "
            f"(model={self._settings.groq_model}). Last rejection — {problem}"
        )

    async def _complete(self, messages: list[dict[str, str]]) -> str:
        """One chat completion, returned as its raw content string."""
        try:
            completion = await self._client.chat.completions.create(
                model=self._settings.groq_model,
                temperature=SAMPLING_TEMPERATURE,
                response_format={"type": "json_object"},
                messages=messages,  # type: ignore[arg-type]
            )
        except RateLimitError as exc:
            # The one failure that carries a *when*. Kept distinct from the 4xx below so the
            # API can answer "wait 20 seconds" instead of "the request was rejected" — on a
            # free tier during judging this is the likeliest failure of the lot.
            raise AgentRateLimited(
                f"Groq rate-limited the request: {str(exc.message)[:300]}",
                retry_after_seconds=_retry_after_seconds(exc),
            ) from exc
        except APIStatusError as exc:
            raise AgentError(
                f"Groq returned HTTP {exc.status_code}: {str(exc.message)[:300]}"
            ) from exc
        except OpenAIError as exc:
            raise AgentError(f"could not reach Groq: {exc}") from exc
        except json.JSONDecodeError as exc:
            # A 200 whose body is not JSON at all: an HTML error page from something in
            # front of Groq, or an empty body. The SDK lets this through unwrapped, and
            # `JSONDecodeError` is not an `OpenAIError`.
            raise AgentError(f"Groq returned a 200 that was not JSON: {exc}") from exc

        content = _reply_content(completion)
        if content is None:
            raise AgentError(
                "Groq returned HTTP 200 but not a chat completion — check GROQ_BASE_URL "
                f"and anything proxying it. Body starts: {str(completion)[:200]!r}"
            )
        return content

