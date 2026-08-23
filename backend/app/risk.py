"""Fixed risk thresholds.

These live in code, not in the LLM prompt's discretion. The prompt states them so the
model's prose stays consistent, but `enforce_thresholds` is what actually decides
(CLAUDE.md → Architecture step 4: "do not let the LLM decide thresholds itself").
"""

from .schemas import AgentDecision, Decision, RiskLevel

# Peak temperature in °C.
MEDIUM_THRESHOLD_C = 30.0
HIGH_THRESHOLD_C = 33.0

_DECISION_FOR_RISK: dict[RiskLevel, Decision] = {
    "LOW": "PROCEED",
    "MEDIUM": "MODIFY",
    "HIGH": "RESCHEDULE",
}


def classify(peak_temperature_c: float) -> RiskLevel:
    """LOW < 30 °C, MEDIUM 30–33 °C, HIGH >= 33 °C."""
    if peak_temperature_c >= HIGH_THRESHOLD_C:
        return "HIGH"
    if peak_temperature_c >= MEDIUM_THRESHOLD_C:
        return "MEDIUM"
    return "LOW"


def decision_for(risk_level: RiskLevel) -> Decision:
    return _DECISION_FOR_RISK[risk_level]


# What an unmeasurable area is treated as. `PROCEED` is a safety claim, and with no reading
# there is nothing to back it — so missing data floors to caution instead of being handed
# to the model to guess. This is a documented default, not a measurement: the temperatures
# stay null so the dashboard still shows the data as unavailable.
UNKNOWN_RISK_LEVEL: RiskLevel = "MEDIUM"

UNKNOWN_REASON = (
    "No usable temperature readings were available for this area, so the shift is treated "
    "as caution by default rather than cleared."
)


def reason_for(peak_temperature_c: float) -> str:
    """A deterministic `reason`, for when the model's own prose cannot be trusted.

    Used when the model reported a temperature that disagreed with the measurement: prose
    narrating a number that just got corrected would contradict the card it sits on.
    """
    if peak_temperature_c >= HIGH_THRESHOLD_C:
        return (
            f"Measured peak of {peak_temperature_c:g} C is at or above the "
            f"{HIGH_THRESHOLD_C:g} C HIGH threshold."
        )
    if peak_temperature_c >= MEDIUM_THRESHOLD_C:
        return (
            f"Measured peak of {peak_temperature_c:g} C falls in the "
            f"{MEDIUM_THRESHOLD_C:g}-{HIGH_THRESHOLD_C:g} C MEDIUM band."
        )
    return (
        f"Measured peak of {peak_temperature_c:g} C is below the "
        f"{MEDIUM_THRESHOLD_C:g} C MEDIUM threshold."
    )


# Fallback guidance, used only when the model argued for a different verdict than the
# thresholds reached. Its own `recommendation` was written to justify that other verdict, so
# it cannot be shown beside the enforced one — the dashboard card and the Slack alert both
# print it verbatim, and "no special heat precautions needed" under a RESCHEDULE header is
# worse than no advice at all. Deliberately generic: this is a floor, not the model's job.
_RECOMMENDATION_FOR_RISK: dict[RiskLevel, str] = {
    "LOW": (
        "Standard hot-weather practice is enough: drinking water at every work position, "
        "breaks on the normal schedule, and closer watch on anyone new to working in heat."
    ),
    "MEDIUM": (
        "Move the heaviest tasks to the coolest part of the window, add a shaded break each "
        "hour, and keep water within arm's reach of the crew."
    ),
    "HIGH": (
        "Move outdoor work out of this window. For anything that cannot be moved, work "
        "short rotations in shade with someone watching the crew for heat illness."
    ),
}


def recommendation_for(risk_level: RiskLevel) -> str:
    """Deterministic guidance for `risk_level`, when the model's own cannot be shown."""
    return _RECOMMENDATION_FOR_RISK[risk_level]


def enforce_thresholds(decision: AgentDecision) -> AgentDecision:
    """Overwrite the model's `risk_level`/`decision` with the deterministic mapping.

    Applied on every path, including the no-reading one, so `risk_level` and `decision` can
    never contradict each other and a go-ahead can never rest on the model's own judgement.

    When the mapping *disagrees* with what the model concluded, its `recommendation` and
    `reason` are replaced too. They were written to argue for the verdict it picked, and the
    dashboard and the Slack alert print them next to the verdict that actually shipped.
    """
    if decision.peak_temperature is None:
        risk_level = UNKNOWN_RISK_LEVEL
        # Replaced, not appended: a model reason written about a temperature it was told to
        # drop would sit next to a blank peak on the card.
        reason = UNKNOWN_REASON
    else:
        risk_level = classify(decision.peak_temperature)
        reason = reason_for(decision.peak_temperature)

    outcome = decision_for(risk_level)
    updates: dict[str, object] = {"risk_level": risk_level, "decision": outcome}

    if (decision.risk_level, decision.decision) != (risk_level, outcome):
        updates["recommendation"] = recommendation_for(risk_level)
        updates["reason"] = reason
    elif decision.peak_temperature is None:
        # The verdict matched, but there is still no temperature for the model's sentence to
        # be about.
        updates["reason"] = reason

    return decision.model_copy(update=updates)

