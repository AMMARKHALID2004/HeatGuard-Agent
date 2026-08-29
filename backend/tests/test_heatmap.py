"""Tests for `summarize_heatmap` — the parser that turns FortyGuard's `data.result` into
peak/average/count/sample.

The live probe (2026-08-29) confirmed the result shape and, crucially, that this parser was
the bug: recent timestamps returned a real but *empty* grid (`features: []`,
`stats_data.n_cells: 0`) while a 2024 control returned 150 cells the old name-based heuristic
mis-summed by sweeping in distribution bins. These tests pin both the confirmed shape and the
generic fallback the tests/stub fixtures rely on.

    uv run python -m unittest tests.test_heatmap -v
"""

import json
import unittest
from typing import Any

from app.services.heatmap import summarize_heatmap


def fortyguard_grid(temps: list[float], *, stats: dict[str, Any] | None = None) -> dict[str, Any]:
    """The confirmed `{map_data: FeatureCollection, stats_data}` shape, one cell per temp."""
    payload: dict[str, Any] = {
        "map_data": {
            "type": "FeatureCollection",
            "features": [
                {
                    "id": str(i),
                    "type": "Feature",
                    "properties": {
                        "tile_id": i,
                        "average_temperature": t,
                        "min_temperature": t,
                        "max_temperature": t,
                    },
                    "geometry": {"type": "Polygon", "coordinates": [[[0, 0]]]},
                }
                for i, t in enumerate(temps)
            ],
        },
        "stats_data": {"n_cells": len(temps)},
    }
    if stats is not None:
        payload["stats_data"]["temperature_stats"] = stats
    return payload


class FortyGuardShapeTests(unittest.TestCase):
    def test_reads_per_cell_readings_by_field(self):
        summary = summarize_heatmap(fortyguard_grid([31.0, 32.0, 33.0]))
        self.assertEqual(summary["reading_count"], 3)
        self.assertEqual(summary["peak_temperature"], 33.0)
        self.assertEqual(summary["average_temperature"], 32.0)
        self.assertEqual(summary["sample"], [31.0, 32.0, 33.0])

    def test_authoritative_stats_win_over_the_sampled_cells(self):
        """`temperature_stats` covers the whole grid, so its peak/mean are preferred over the
        max/mean of the per-cell field we happened to sample."""
        summary = summarize_heatmap(
            fortyguard_grid(
                [31.9, 32.2],
                stats={"maximum": 33.1424, "mean": 32.2552, "minimum": 31.887},
            )
        )
        self.assertEqual(summary["peak_temperature"], 33.14)
        self.assertEqual(summary["average_temperature"], 32.26)
        self.assertEqual(summary["reading_count"], 2)

    def test_ignores_distribution_bins_that_merely_contain_temperature_in_their_key(self):
        """The regression: `normal_temperature_distribution` / `temperature_frequency` are
        histogram bins, not readings. An empty grid carrying them must still read as no data,
        not as a grid full of phantom temperatures."""
        payload = {
            "map_data": {"type": "FeatureCollection", "features": []},
            "stats_data": {
                "n_cells": 0,
                "overall_temperature_distribution": [31.8, 32.0, 33.1],
                "temperature_frequency": {"x_axis": [32.0, 33.0], "y_axis": [111, 39]},
            },
        }
        summary = summarize_heatmap(payload)
        self.assertEqual(summary["reading_count"], 0)
        self.assertIsNone(summary["peak_temperature"])
        self.assertIsNone(summary["average_temperature"])

    def test_an_empty_grid_is_a_real_no_data_result(self):
        summary = summarize_heatmap(
            {"map_data": {"type": "FeatureCollection", "features": []}, "stats_data": {"n_cells": 0}}
        )
        self.assertEqual(summary["reading_count"], 0)
        self.assertIsNone(summary["peak_temperature"])

    def test_a_json_encoded_result_string_is_decoded_first(self):
        summary = summarize_heatmap(json.dumps(fortyguard_grid([30.0, 40.0])))
        self.assertEqual(summary["reading_count"], 2)
        self.assertEqual(summary["peak_temperature"], 40.0)


class GenericFallbackTests(unittest.TestCase):
    """Shapes other than FortyGuard's — the fixtures the suite and the loopback stub use."""

    def test_cells_fixture_still_parses(self):
        summary = summarize_heatmap({"cells": [{"temperature": 41.2}, {"temperature": 38.4}]})
        self.assertEqual(summary["reading_count"], 2)
        self.assertEqual(summary["peak_temperature"], 41.2)
        self.assertEqual(summary["average_temperature"], 39.8)

    def test_empty_cells_is_no_data(self):
        summary = summarize_heatmap({"cells": []})
        self.assertEqual(summary["reading_count"], 0)
        self.assertIsNone(summary["peak_temperature"])

    def test_bare_nested_grid(self):
        summary = summarize_heatmap({"temperature_grid": [[31.1, 32.4], [33.0]]})
        self.assertEqual(summary["reading_count"], 3)
        self.assertEqual(summary["peak_temperature"], 33.0)

    def test_nested_stats_object_is_not_mistaken_for_readings(self):
        summary = summarize_heatmap({"temperature": {"peak": 41.2, "grid_id": 7}})
        self.assertEqual(summary["reading_count"], 0)
        self.assertIsNone(summary["peak_temperature"])


if __name__ == "__main__":
    unittest.main()
