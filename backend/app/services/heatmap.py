"""Reduce a FortyGuard heatmap result (`data.result`) to something small enough to reason over.

A heatmap can carry a large grid of readings. Sending all of it to the LLM is slow and
wasteful, so the temperature values are extracted here and the model receives statistics
plus a small sample. The n8n prototype instead stringified the entire payload into the
prompt and let the model find the peak itself — that is the fragility this replaces.

TODO(fortyguard-docs): the walk below is a shape-agnostic heuristic, because the exact
result schema is unconfirmed (the prototype export carries no `pinData`, so it holds no
recorded response). Once the shape is known, replace `_collect_temperatures` with direct
field access — that removes both failure modes described below.

The heuristic collects a number only when its own key names a temperature, and only
descends through *lists* while that hint holds. So it handles:

    {"cells": [{"temperature": 41.2}, ...]}      -> per-cell readings
    {"temperature_grid": [[31.1, 32.4], [33.0]]} -> bare nested values

but deliberately not:

    {"temperature": {"peak": 41.2, "grid_id": 7}} -> nested stats object

Descending into a dict under a temperature hint would also swallow neighbouring ids and
counts, which sit in the same plausible numeric range and would quietly skew the average.
Missing that shape yields `null` temperatures, which the dashboard shows as unavailable —
a visible gap rather than a confidently wrong answer. `reading_count` is returned so a
mis-parse is obvious at a glance.
"""

import json
import logging
from statistics import fmean
from typing import Any

logger = logging.getLogger(__name__)

# Values outside this band are units, ids, or coordinates — not Celsius air temperatures.
_PLAUSIBLE_C_RANGE = (-90.0, 90.0)
_TEMP_KEY_HINT = "temp"
_SAMPLE_SIZE = 24


def _is_plausible_celsius(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    low, high = _PLAUSIBLE_C_RANGE
    return low <= float(value) <= high


def _coerce(payload: Any) -> Any:
    """Decode a JSON-encoded result.

    The prototype's `Edit Fields` node assigned `data.result` with `type: "string"`, so the
    heatmap can arrive already serialized.
    """
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except ValueError:
            logger.warning("Heatmap result was a string but not valid JSON")
            return None
    return payload


def _collect_temperatures(node: Any, *, under_temp_key: bool = False) -> list[float]:
    """Collect plausible Celsius readings. See the module docstring for the rules."""
    found: list[float] = []

    if isinstance(node, dict):
        for key, value in node.items():
            # Each key is judged on its own name; the hint does not cross into a dict.
            hinted = _TEMP_KEY_HINT in key.lower()
            if hinted and _is_plausible_celsius(value):
                found.append(float(value))
            else:
                found.extend(_collect_temperatures(value, under_temp_key=hinted))
    elif isinstance(node, list):
        for item in node:
            if under_temp_key and _is_plausible_celsius(item):
                found.append(float(item))
            else:
                found.extend(_collect_temperatures(item, under_temp_key=under_temp_key))

    return found


def summarize_heatmap(payload: Any) -> dict[str, Any]:
    """Return `{peak_temperature, average_temperature, reading_count, sample}`.

    Temperatures are `None` when the payload held no usable readings, so the agent reports
    missing data instead of inventing a number.
    """
    temperatures = _collect_temperatures(_coerce(payload))
    if not temperatures:
        logger.warning(
            "No temperature readings found in the heatmap result (type=%s, keys=%s)",
            type(payload).__name__,
            sorted(payload)[:20] if isinstance(payload, dict) else "n/a",
        )
        return {
            "peak_temperature": None,
            "average_temperature": None,
            "reading_count": 0,
            "sample": [],
        }

    step = max(1, len(temperatures) // _SAMPLE_SIZE)
    return {
        "peak_temperature": round(max(temperatures), 2),
        "average_temperature": round(fmean(temperatures), 2),
        "reading_count": len(temperatures),
        "sample": [round(value, 2) for value in temperatures[::step][:_SAMPLE_SIZE]],
    }
