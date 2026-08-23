"""Groq (OpenAI-compatible) agent reasoning step.

The model writes the plain-language `recommendation` and `reason`. Its `risk_level` and
`decision` are re-derived from the fixed thresholds in `app.risk` afterwards, so a
hallucinated classification cannot reach the dashboard.
"""

import json
import logging
from datetime import datetime
from typing import Any

import httpx
from pydantic import ValidationError

from ..config import Settings
from ..risk import HIGH_THRESHOLD_C, MEDIUM_THRESHOLD_C
from ..schemas import AgentDecision

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    """Groq was unreachable, or its output did not match the agent schema."""


SYSTEM_PROMPT = f"""\
You are HeatGuard, a heat-safety agent for outdoor construction crews.

You receive temperature statistics for one work area and one work window, and you output
a go/no-go decision for the shift.

Classify strictly by PEAK temperature in Celsius — these thresholds are fixed, never
adjust or reinterpret them:
- LOW:    peak < {MEDIUM_THRESHOLD_C} C          -> decision "PROCEED"
- MEDIUM: peak >= {MEDIUM_THRESHOLD_C} C and < {HIGH_THRESHOLD_C} C -> decision "MODIFY"
- HIGH:   peak >= {HIGH_THRESHOLD_C} C           -> decision "RESCHEDULE"

Rules:
- Use only the temperatures provided. If a temperature is missing, return null for it and
  say so in `reason`. Never invent or estimate a value.
- `recommendation` is one or two sentences of concrete crew guidance a site supervisor can
  act on (shift timing, hydration and rest cadence, shade, task swaps). No hedging.
- `reason` states the numbers and the threshold they crossed, in one sentence.

Reply with JSON only, exactly these keys:
{{"risk_level": "LOW|MEDIUM|HIGH", "peak_temperature": number|null,
  "average_temperature": number|null, "decision": "PROCEED|MODIFY|RESCHEDULE",
  "recommendation": string, "reason": string}}
"""


def _build_user_prompt(summary: dict[str, Any], date_time: datetime) -> str:
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


async def reason_about_heat(
    settings: Settings,
    *,
    summary: dict[str, Any],
    date_time: datetime,
) -> AgentDecision:
    """Ask Groq for the decision JSON and validate it against `AgentDecision`."""
    if not settings.groq_api_key:
        raise LLMError("GROQ_API_KEY is not set")

    request_body = {
        "model": settings.groq_model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(summary, date_time)},
        ],
    }

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        response = await client.post(
            f"{settings.groq_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json=request_body,
        )

    if response.is_error:
        raise LLMError(f"Groq returned HTTP {response.status_code}: {response.text[:300]}")

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"unexpected Groq response envelope: {exc}") from exc

    try:
        return AgentDecision.model_validate_json(content)
    except ValidationError as exc:
        logger.warning("Groq output failed schema validation: %s", content[:500])
        raise LLMError(f"Groq output did not match the agent schema: {exc}") from exc
