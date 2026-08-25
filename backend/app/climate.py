"""US climate-zone thresholds — the editable heat-risk lookup table.

Heat-mortality research shows the temperature at which outdoor work turns dangerous
shifts with regional acclimatization: 33 °C is a serious risk in Minnesota but an
ordinary summer afternoon in Phoenix. A single national cutoff is therefore confidently
wrong outside the region it was tuned for. This module resolves a US state to a climate
zone and that zone's two peak-temperature thresholds.

This is a plain lookup table on purpose (CLAUDE.md → "simple, clearly editable config,
not buried in agent logic"). To retune a zone, edit its numbers below; to move a state to
a different zone, edit `STATE_TO_ZONE`. The thresholds are still *enforced* in `app.risk`
and only mirrored to the LLM — the model never picks them.

Each zone stores the same two numbers `app.risk` classifies on:

- `medium_threshold_c` — the LOW/MEDIUM boundary (a peak at or above this is at least MEDIUM)
- `high_threshold_c`   — the MEDIUM/HIGH boundary (a peak at or above this is HIGH)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClimateZone:
    """One region's heat-risk banding. Frozen so a resolved zone can't be mutated."""

    name: str
    medium_threshold_c: float
    high_threshold_c: float


# The four zones, keyed by a stable slug. Thresholds are peak temperature in °C:
#   LOW  peak < medium
#   MEDIUM  medium <= peak < high
#   HIGH  peak >= high
ZONES: dict[str, ClimateZone] = {
    "hot-humid": ClimateZone("Hot-Humid", 34.0, 37.0),
    "hot-dry": ClimateZone("Hot-Dry", 36.0, 39.0),
    "mixed-humid": ClimateZone("Mixed-Humid", 30.0, 33.0),
    "cold-northern": ClimateZone("Cold / Northern", 27.0, 30.0),
}

# The national default, applied to any site we can't place in a hotter or colder zone.
# 30/33 keeps the originally tested Northeast behavior byte-for-byte.
DEFAULT_ZONE: ClimateZone = ZONES["mixed-humid"]

# Only states that differ from the Mixed-Humid default are listed; everything unlisted
# (including NY / NYC, the demo site) falls back to `DEFAULT_ZONE`. Two-letter USPS codes.
#
# Judgment calls worth knowing (one-line edits to move):
#   TX -> Hot-Humid: the Gulf coast and most of the population are humid; far-west TX
#         (El Paso) is really Hot-Dry, but state-level resolution picks the majority.
#   CA -> Hot-Dry:   matches the "southern CA" desert example; the cool coast is milder,
#         but the state-level call errs toward the hot inland sites that need the care.
STATE_TO_ZONE: dict[str, ClimateZone] = {
    # Hot-Humid — Gulf and Southeast
    "FL": ZONES["hot-humid"],
    "LA": ZONES["hot-humid"],
    "MS": ZONES["hot-humid"],
    "AL": ZONES["hot-humid"],
    "GA": ZONES["hot-humid"],
    "SC": ZONES["hot-humid"],
    "TX": ZONES["hot-humid"],
    # Hot-Dry — desert Southwest
    "AZ": ZONES["hot-dry"],
    "NV": ZONES["hot-dry"],
    "NM": ZONES["hot-dry"],
    "CA": ZONES["hot-dry"],
    # Cold / Northern — the northern tier
    "MN": ZONES["cold-northern"],
    "ME": ZONES["cold-northern"],
    "WA": ZONES["cold-northern"],
    "OR": ZONES["cold-northern"],
    "MT": ZONES["cold-northern"],
    "ND": ZONES["cold-northern"],
    "SD": ZONES["cold-northern"],
    "WI": ZONES["cold-northern"],
    "MI": ZONES["cold-northern"],
    "ID": ZONES["cold-northern"],
    "WY": ZONES["cold-northern"],
    "VT": ZONES["cold-northern"],
    "NH": ZONES["cold-northern"],
    "AK": ZONES["cold-northern"],
}


def resolve_zone(state: str | None) -> ClimateZone:
    """Map a US state (USPS code, any case/whitespace) to its zone, else the default.

    Unknown, blank, or missing state -> `DEFAULT_ZONE`, so an unplaceable location still
    gets the safe Northeast banding rather than failing the request.
    """
    if not state:
        return DEFAULT_ZONE
    return STATE_TO_ZONE.get(state.strip().upper(), DEFAULT_ZONE)


# Full state-name -> USPS code, for when Nominatim gives a name but no ISO code.
_STATE_NAME_TO_CODE: dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "florida": "FL", "georgia": "GA", "hawaii": "HI",
    "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME",
    "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM",
    "new york": "NY", "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI",
    "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def state_code_from_nominatim(address: dict) -> str | None:
    """Pull a two-letter US state code out of a Nominatim `address` object.

    Prefers the ISO 3166-2 subdivision code Nominatim returns for US states
    (`ISO3166-2-lvl4`, e.g. "US-AZ"); falls back to matching the spelled-out `state`
    name. Returns `None` when neither is present or recognized — which `resolve_zone`
    then treats as the default zone.
    """
    iso = address.get("ISO3166-2-lvl4")
    if isinstance(iso, str) and iso.upper().startswith("US-"):
        code = iso.split("-", 1)[1].strip().upper()
        if code:
            return code
    name = address.get("state")
    if isinstance(name, str):
        return _STATE_NAME_TO_CODE.get(name.strip().lower())
    return None
