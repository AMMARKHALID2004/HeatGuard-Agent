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
  (CLAUDE.md → "do not let the LLM decide thresholds itself").

That leaves the model responsible for exactly what it is good at: the plain-language
`recommendation` and `reason`.

A reply that is not valid JSON, or does not fit `AgentDecision`, is handed back once as a
repair turn quoting the validation error. A second failure raises `AgentError`.
"""

import json
import logging
from datetime import datetime
from types import TracebackType
from typing import Any, Self

from openai import APIStatusError, AsyncOpenAI, OpenAIError
from pydantic import ValidationError

from .config import Settings
from .risk import HIGH_THRESHOLD_C, MEDIUM_THRESHOLD_C, enforce_thresholds
from .schemas import AgentDecision
from .services.heatmap import summarize_heatmap

logger = logging.getLogger(__name__)

# One initial call plus one repair turn. This counts *schema* attempts.
MAX_ATTEMPTS = 2

# Retries the SDK performs itself for transient transport failures — 429s and 5xx, with
# backoff that respects Retry-After. Groq's free tier does rate-limit, so this is worth
# keeping during judging. Orthogonal to MAX_ATTEMPTS: a 200 carrying malformed JSON is not
# a transport failure and is never retried here.
SDK_MAX_RETRIES = 2

# Low but non-zero: the decision is deterministic, only the prose should vary.
SAMPLING_TEMPERATURE = 0.2

# How much of an offending reply to put in the log.
_LOG_EXCERPT = 400


class AgentError(RuntimeError):
    """Groq was unreachable, misconfigured, or never produced a usable decision."""


class _UnusableReply(Exception):
    """Internal: this reply cannot become an `AgentDecision`, so it earns a repair turn."""


SYSTEM_PROMPT = f"""\
You are HeatGuard, a heat-safety agent for outdoor construction crews. You are given
temperature statistics for one work area and one work window, and you return a go/no-go
decision for that shift.

Classify on PEAK temperature in Celsius. These thresholds are fixed — never adjust them,
reinterpret them, or substitute your own judgement:

  risk_level   peak temperature                  decision
  LOW          peak < {MEDIUM_THRESHOLD_C:g} C                        PROCEED
  MEDIUM       {MEDIUM_THRESHOLD_C:g} C <= peak < {HIGH_THRESHOLD_C:g} C              MODIFY
  HIGH         peak >= {HIGH_THRESHOLD_C:g} C                       RESCHEDULE

Never invent, estimate, extrapolate, or fill in a temperature. Use only the numbers you
were given. If a temperature was not provided, return null for it and say it was
unavailable in `reason`. A null is always better than a guess.

Write `recommendation` as one or two sentences of concrete guidance a site supervisor can
act on today: shift timing, hydration and rest cadence, shade, task swaps. No hedging.
Write `reason` as one sentence naming the peak temperature and the threshold it crossed.

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


def build_user_prompt(summary: dict[str, Any], date_time: datetime) -> str:
    """Hand the model the measured statistics — never the raw grid."""
    return json.dumps(
        {
            "work_window_start": date_time.isoformat(),
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


def _reconcile(decision: AgentDecision, summary: dict[str, Any]) -> AgentDecision:
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
        decision = decision.model_copy(update=updates)
    return enforce_thresholds(decision)


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
            raise AgentError("GROQ_API_KEY is not set")
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

    async def assess(self, heatmap: Any, *, date_time: datetime) -> AgentDecision:
        """Summarize `heatmap`, reason about it, and return a validated decision.

        Raises `AgentError` if Groq is unreachable or misconfigured, or if it fails to
        produce a schema-valid decision within `MAX_ATTEMPTS`.
        """
        summary = summarize_heatmap(heatmap)
        logger.info(
            "Assessing heatmap: readings=%s peak=%s average=%s",
            summary["reading_count"],
            summary["peak_temperature"],
            summary["average_temperature"],
        )

        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(summary, date_time)},
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

            return _reconcile(decision, summary)

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
        except APIStatusError as exc:
            raise AgentError(
                f"Groq returned HTTP {exc.status_code}: {str(exc.message)[:300]}"
            ) from exc
        except OpenAIError as exc:
            raise AgentError(f"could not reach Groq: {exc}") from exc

        if not completion.choices:
            logger.warning("Groq returned no choices")
            return ""

        choice = completion.choices[0]
        if choice.finish_reason == "length":
            logger.warning("Groq reply hit the token limit and is probably truncated")
        return choice.message.content or ""
