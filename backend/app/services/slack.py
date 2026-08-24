"""Slack Incoming Webhook alerting for RESCHEDULE decisions.

Alerting is best-effort: a failed Slack post is logged but never fails the evaluation,
because the dashboard still needs to show the decision.
"""

import logging

import httpx

from ..config import Settings
from ..schemas import AgentDecision

logger = logging.getLogger(__name__)

_EMOJI = {"LOW": ":large_green_circle:", "MEDIUM": ":large_yellow_circle:", "HIGH": ":red_circle:"}


def _format_temperature(value: float | None) -> str:
    return f"{value:.1f} °C" if value is not None else "unavailable"


def _build_message(decision: AgentDecision) -> dict[str, object]:
    emoji = _EMOJI.get(decision.risk_level, ":thermometer:")
    return {
        "text": f"{emoji} HeatGuard: {decision.decision} — {decision.risk_level} heat risk",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"HeatGuard: {decision.decision}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Risk level*\n{decision.risk_level}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Peak*\n{_format_temperature(decision.peak_temperature)}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Average*\n{_format_temperature(decision.average_temperature)}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Recommendation*\n{decision.recommendation}"},
            },
            {
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": decision.reason}],
            },
        ],
    }


async def send_alert(
    settings: Settings,
    decision: AgentDecision,
    *,
    http_client: httpx.AsyncClient | None = None,
) -> bool:
    """Post the decision to Slack. Returns whether the alert was delivered.

    Pass `http_client` to supply your own transport — the same injection point
    `FortyGuardClient` and `HeatRiskAgent` offer, and how the tests drive this offline.
    """
    if not settings.slack_webhook_url:
        logger.info("SLACK_WEBHOOK_URL not set — skipping alert")
        return False

    try:
        if http_client is not None:
            response = await http_client.post(
                settings.slack_webhook_url, json=_build_message(decision)
            )
        else:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
                response = await client.post(
                    settings.slack_webhook_url, json=_build_message(decision)
                )
        if response.is_error:
            logger.error("Slack webhook returned HTTP %s: %s", response.status_code, response.text[:200])
            return False
    except Exception as exc:  # noqa: BLE001 — see below
        # Deliberately broad, and the reason is a real bug this caught: `httpx.InvalidURL`
        # inherits from `Exception`, NOT from `httpx.HTTPError`, so `SLACK_WEBHOOK_URL` with
        # a typo'd port ("https://hooks.slack.com:notaport/...") escaped a narrower handler
        # and 500'd the whole evaluation. That discarded a valid RESCHEDULE — the one verdict
        # that matters most — because a *notification* was misconfigured. idna's
        # `InvalidCodepoint` escapes the same way. Alerting is best-effort by contract, so
        # nothing raised in here may take the decision down with it.
        logger.error("Slack webhook post failed (%s): %s", type(exc).__name__, exc)
        return False

    logger.info("Slack alert delivered for %s decision", decision.decision)
    return True
