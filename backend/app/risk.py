"""Fixed risk thresholds, resolved per climate zone.

These live in code, not in the LLM prompt's discretion. The prompt states them so the
model's prose stays consistent, but `enforce_thresholds` is what actually decides
(CLAUDE.md → Architecture step 4: "do not let the LLM decide thresholds itself").

The two cutoffs are no longer national: they come from the site's `ClimateZone`
(`app.climate`), because a peak that is safe in Phoenix is dangerous in Minnesota. Every
function takes a `zone`, defaulting to `DEFAULT_ZONE` (Mixed-Humid, 30/33), so callers and
tests that predate zones keep the original Northeast behavior unchanged.
"""

from .climate import DEFAULT_ZONE, ClimateZone
from .schemas import AgentDecision, Decision, RiskLevel

# The default zone's cutoffs, kept as module constants for any caller still referencing
# the old national numbers. Peak temperature in °C.
MEDIUM_THRESHOLD_C = DEFAULT_ZONE.medium_threshold_c
HIGH_THRESHOLD_C = DEFAULT_ZONE.high_threshold_c

_DECISION_FOR_RISK: dict[RiskLevel, Decision] = {
    "LOW": "PROCEED",
    "MEDIUM": "MODIFY",
    "HIGH": "RESCHEDULE",
    "UNKNOWN": "NO_DATA",
}


def classify(peak_temperature_c: float, zone: ClimateZone = DEFAULT_ZONE) -> RiskLevel:
    """LOW below the zone's MEDIUM cutoff, MEDIUM up to its HIGH cutoff, HIGH at or above."""
    if peak_temperature_c >= zone.high_threshold_c:
        return "HIGH"
    if peak_temperature_c >= zone.medium_threshold_c:
        return "MEDIUM"
    return "LOW"


def decision_for(risk_level: RiskLevel) -> Decision:
    return _DECISION_FOR_RISK[risk_level]


# What an unmeasurable area is treated as. `PROCEED` is a safety claim, and with no reading
# there is nothing to back it — so missing data floors to caution instead of being handed
# to the model to guess. This is a documented default, not a measurement: the temperatures
# stay null so the dashboard still shows the data as unavailable.
UNKNOWN_RISK_LEVEL: RiskLevel = "UNKNOWN"

NO_DATA_REASON = (
    "FortyGuard returned no temperature readings for this area and time. The API may not have "
    "data for early morning hours. Try a later time window or verify conditions on-site."
)


def reason_for(peak_temperature_c: float, zone: ClimateZone = DEFAULT_ZONE) -> str:
    """A deterministic `reason`, for when the model's own prose cannot be trusted.

    Used when the model reported a temperature that disagreed with the measurement: prose
    narrating a number that just got corrected would contradict the card it sits on. Names
    the zone so the sentence explains why this cutoff and not the national one.
    """
    if peak_temperature_c >= zone.high_threshold_c:
        return (
            f"Measured peak of {peak_temperature_c:g} C is at or above the "
            f"{zone.high_threshold_c:g} C HIGH threshold for the {zone.name} zone."
        )
    if peak_temperature_c >= zone.medium_threshold_c:
        return (
            f"Measured peak of {peak_temperature_c:g} C falls in the "
            f"{zone.medium_threshold_c:g}-{zone.high_threshold_c:g} C MEDIUM band for the "
            f"{zone.name} zone."
        )
    return (
        f"Measured peak of {peak_temperature_c:g} C is below the "
        f"{zone.medium_threshold_c:g} C MEDIUM threshold for the {zone.name} zone."
    )


# Fallback guidance, used only when the model argued for a different verdict than the
# thresholds reached. Its own `recommendation` was written to justify that other verdict, so
# it cannot be shown beside the enforced one — the dashboard card and the Slack alert both
# print it verbatim, and "no special heat precautions needed" under a RESCHEDULE header is
# worse than no advice at all. Deliberately generic: this is a floor, not the model's job.
# Keyed on `risk_level` alone — the guidance is about the band, not the zone's exact cutoff.
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
    "UNKNOWN": (
        "No temperature data available from FortyGuard for this time. Try a later shift "
        "window (midday–afternoon) or verify conditions on-site before committing the crew."
    ),
}


def recommendation_for(risk_level: RiskLevel) -> str:
    """Deterministic guidance for `risk_level`, when the model's own cannot be shown."""
    return _RECOMMENDATION_FOR_RISK[risk_level]


def enforce_thresholds(
    decision: AgentDecision, zone: ClimateZone = DEFAULT_ZONE
) -> AgentDecision:
    """Overwrite the model's `risk_level`/`decision` with the deterministic mapping.

    Applied on every path, including the no-reading one, so `risk_level` and `decision` can
    never contradict each other and a go-ahead can never rest on the model's own judgement.
    Classification uses `zone`'s thresholds, so the same peak can land in different bands
    depending on where the site is.

    When the mapping *disagrees* with what the model concluded, its `recommendation` and
    `reason` are replaced too. They were written to argue for the verdict it picked, and the
    dashboard and the Slack alert print them next to the verdict that actually shipped.
    """
    if decision.peak_temperature is None:
        risk_level = UNKNOWN_RISK_LEVEL
        reason = NO_DATA_REASON
    else:
        risk_level = classify(decision.peak_temperature, zone)
        reason = reason_for(decision.peak_temperature, zone)

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
