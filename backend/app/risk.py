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


def enforce_thresholds(decision: AgentDecision) -> AgentDecision:
    """Overwrite the model's `risk_level`/`decision` with the deterministic mapping.

    When the peak temperature is unknown there is no number to threshold against, so the
    model's own classification is left in place — the null temperatures make the
    uncertainty visible on the dashboard.
    """
    if decision.peak_temperature is None:
        return decision

    risk_level = classify(decision.peak_temperature)
    return decision.model_copy(
        update={"risk_level": risk_level, "decision": decision_for(risk_level)}
    )
