"""Tests for `app.climate` — the state -> climate-zone -> thresholds lookup table.

This is the editable heat-risk config, and it's the single source of truth both the agent
and the dashboard read (the frontend only displays what the API resolved). So the mapping
itself is worth pinning: a wrong entry here quietly ships a wrong go/no-go call.

    uv run python -m unittest discover -v
"""

import unittest

from app.climate import (
    DEFAULT_ZONE,
    ZONES,
    resolve_zone,
    state_code_from_nominatim,
)


class ResolveZoneTests(unittest.TestCase):
    def test_known_states_map_to_their_zone(self):
        cases = {
            "AZ": "hot-dry",
            "CA": "hot-dry",
            "FL": "hot-humid",
            "TX": "hot-humid",   # documented judgment call: Gulf/majority is humid
            "MN": "cold-northern",
            "AK": "cold-northern",
        }
        for state, slug in cases.items():
            with self.subTest(state=state):
                self.assertIs(resolve_zone(state), ZONES[slug])

    def test_resolution_ignores_case_and_surrounding_whitespace(self):
        for raw in ("az", "Az", " AZ ", "  az\n"):
            with self.subTest(raw=repr(raw)):
                self.assertIs(resolve_zone(raw), ZONES["hot-dry"])

    def test_an_unlisted_state_falls_back_to_the_default(self):
        """NY is deliberately not in the table — the default *is* Mixed-Humid (30/33)."""
        zone = resolve_zone("NY")
        self.assertIs(zone, DEFAULT_ZONE)
        self.assertEqual(zone.name, "Mixed-Humid")
        self.assertEqual((zone.medium_threshold_c, zone.high_threshold_c), (30.0, 33.0))

    def test_none_and_blank_fall_back_to_the_default(self):
        for value in (None, "", "   "):
            with self.subTest(value=repr(value)):
                self.assertIs(resolve_zone(value), DEFAULT_ZONE)

    def test_an_unrecognized_code_falls_back_rather_than_raising(self):
        # A bad or foreign code must degrade to the safe Northeast banding, not 500.
        self.assertIs(resolve_zone("ZZ"), DEFAULT_ZONE)
        self.assertIs(resolve_zone("Ontario"), DEFAULT_ZONE)


class StateCodeFromNominatimTests(unittest.TestCase):
    def test_the_iso_subdivision_code_is_preferred(self):
        self.assertEqual(state_code_from_nominatim({"ISO3166-2-lvl4": "US-AZ"}), "AZ")

    def test_the_iso_code_is_read_case_insensitively(self):
        self.assertEqual(state_code_from_nominatim({"ISO3166-2-lvl4": "us-az"}), "AZ")

    def test_it_falls_back_to_the_spelled_out_state_name(self):
        self.assertEqual(state_code_from_nominatim({"state": "Arizona"}), "AZ")
        self.assertEqual(state_code_from_nominatim({"state": "new york"}), "NY")

    def test_the_iso_code_wins_over_a_conflicting_name(self):
        address = {"ISO3166-2-lvl4": "US-CA", "state": "Arizona"}
        self.assertEqual(state_code_from_nominatim(address), "CA")

    def test_a_non_us_iso_code_is_ignored(self):
        # "CA-ON" is Ontario, Canada — not California. With no US name it resolves to None.
        self.assertIsNone(state_code_from_nominatim({"ISO3166-2-lvl4": "CA-ON"}))
        self.assertIsNone(
            state_code_from_nominatim({"ISO3166-2-lvl4": "CA-ON", "state": "Ontario"})
        )

    def test_an_unknown_or_absent_state_yields_none(self):
        self.assertIsNone(state_code_from_nominatim({}))
        self.assertIsNone(state_code_from_nominatim({"state": "Nowhereland"}))

    def test_a_resolved_code_flows_through_to_a_zone(self):
        """The two functions compose: what Nominatim gives becomes a real zone."""
        code = state_code_from_nominatim({"ISO3166-2-lvl4": "US-FL"})
        self.assertIs(resolve_zone(code), ZONES["hot-humid"])


if __name__ == "__main__":
    unittest.main()
