"""Live probe: which timestamps does FortyGuard actually have data for, and in what shape?

Answers the two questions a "no temperature readings" card cannot distinguish between:

  1. Does FortyGuard have data for near-real-time requests at all, and how far back is the
     freshest reading? (`now` may sit in a processing gap even though the request is valid.)
  2. When a request *does* return a grid, does `app.services.heatmap` actually find the
     temperatures in it — or is it a real payload our parser walks straight past?

Question 2 matters most: both failures look identical on the dashboard. So every probe also
runs a census of every plausible-Celsius number in the raw payload, grouped by JSON path, and
saves the raw result to disk. If the census finds numbers the parser did not, the bug is ours.

Run it from `backend/` (it reads FORTYGUARD_API_KEY from backend/.env; it never prints it):

    uv run python scripts/probe_fortyguard.py

Uses FortyGuard credits: one heatmap job per probe (10 by default, run 3 at a time).
Narrow it while iterating with `--offsets 0,-3,-24` (hours from now, `d` suffix for days).

    uv run python scripts/probe_fortyguard.py --offsets 0,-1,-6,-24,-48 --filter-types 1,2
    uv run python scripts/probe_fortyguard.py --lat 33.45 --lon -112.07   # Phoenix

Exit codes: 0 at least one probe returned readings, 1 every probe came back empty,
2 no API key configured.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from app.config import Settings  # noqa: E402
from app.services.fortyguard import (  # noqa: E402
    FortyGuardClient,
    FortyGuardError,
)
from app.services.heatmap import summarize_heatmap  # noqa: E402
# The dashboard's default demo AOI (Lower Manhattan), so a probe reproduces exactly what the
# "Now" button sends. `--lat/--lon` builds an equivalent box elsewhere.
DEMO_RING = [
    [-74.017, 40.705],
    [-74.003, 40.705],
    [-74.003, 40.718],
    [-74.017, 40.718],
    [-74.017, 40.705],
]

# Hour offsets from now, negative = into the past. The spread matters more than the density:
# it separates "data lags by an hour" from "data lags by days" in a single run.
DEFAULT_OFFSETS_HOURS = [0.0, -1.0, -3.0, -6.0, -12.0, -24.0, -48.0, 3.0, 12.0]

# A timestamp known to have worked in the n8n prototype, as a control: if this one returns
# readings and the recent ones do not, the parser is fine and the data is simply not fresh.
CONTROL_WHEN = datetime(2024, 7, 15, 14, 0)

# Same band `app.services.heatmap` accepts, so the census sees what the parser could have.
_PLAUSIBLE_C = (-90.0, 90.0)


def _census(node: Any, path: str = "$", into: dict[str, list[float]] | None = None) -> dict[str, list[float]]:
    """Group every plausible-Celsius number in the payload by its JSON path.

    List indices collapse to `[]`, so 4 000 grid cells report as one path with 4 000 values.
    Unlike the parser this ignores key *names* entirely — that is the point: it shows what a
    name-based walk would have missed.
    """
    found = into if into is not None else defaultdict(list)

    if isinstance(node, dict):
        for key, value in node.items():
            _census(value, f"{path}.{key}", found)
    elif isinstance(node, list):
        for item in node:
            _census(item, f"{path}[]", found)
    elif not isinstance(node, bool) and isinstance(node, (int, float)):
        low, high = _PLAUSIBLE_C
        if low <= float(node) <= high:
            found[path].append(float(node))

    return found


def _decode(result: Any) -> Any:
    """`data.result` can arrive as a JSON string; the census needs the decoded object."""
    if isinstance(result, str):
        try:
            return json.loads(result)
        except ValueError:
            return result
    return result


def _describe(result: Any) -> str:
    """One line naming the top level of the payload, before any interpretation."""
    if isinstance(result, dict):
        return f"dict keys={sorted(result)[:12]}"
    if isinstance(result, list):
        return f"list len={len(result)}"
    return f"{type(result).__name__}"


class Probe:
    """One (label, timestamp, filter_type) request and whatever came back."""

    def __init__(self, label: str, when: datetime, filter_type: int):
        self.label = label
        self.when = when
        self.filter_type = filter_type
        self.error: str | None = None
        self.raw: Any = None
        self.summary: dict[str, Any] = {}
        self.census: dict[str, list[float]] = {}

    @property
    def parsed_count(self) -> int:
        return int(self.summary.get("reading_count", 0) or 0)

    @property
    def census_count(self) -> int:
        return sum(len(values) for values in self.census.values())

    @property
    def verdict(self) -> str:
        if self.error:
            return f"ERROR   {self.error[:80]}"
        if self.parsed_count:
            return f"DATA    peak={self.summary['peak_temperature']} avg={self.summary['average_temperature']} n={self.parsed_count}"
        if self.census_count:
            return f"MISSED  {self.census_count} number(s) present, parser found 0"
        return "EMPTY   no numbers in the payload at all"


async def run_probe(
    probe: Probe, ring: list[list[float]], settings: Settings, granularity: int, gate: asyncio.Semaphore
) -> Probe:
    """Submit one heatmap job, wait for it, and record what came back."""
    async with gate:
        print(f"  submitting {probe.label} ({probe.when:%Y-%m-%d %H:%M}, filter_type={probe.filter_type})...", flush=True)
        try:
            async with FortyGuardClient(settings) as client:
                _, result = await client.fetch_heatmap(
                    polygon_aoi=ring,
                    date_time=probe.when,
                    filter_type=probe.filter_type,
                    granularity=granularity,
                )
        except (FortyGuardError, httpx.HTTPError, httpx.InvalidURL, OSError) as exc:
            # `httpx.InvalidURL` does not inherit from `HTTPError`, hence both.
            probe.error = f"{type(exc).__name__}: {exc}"
            return probe

    probe.raw = _decode(result)
    probe.summary = summarize_heatmap(result)
    probe.census = dict(_census(probe.raw))
    return probe


def parse_offsets(raw: str) -> list[float]:
    """`"0,-3,-2d"` -> `[0.0, -3.0, -48.0]` hours. A `d` suffix means days."""
    offsets: list[float] = []
    for chunk in raw.split(","):
        token = chunk.strip().lower()
        if not token:
            continue
        if token.endswith("d"):
            offsets.append(float(token[:-1]) * 24)
        else:
            offsets.append(float(token))
    return offsets


def box_around(lat: float, lon: float, size_km: float) -> list[list[float]]:
    """A closed AOI ring roughly `size_km` on a side, centred on the point."""
    half_lat = (size_km / 2) / 111.0
    half_lon = (size_km / 2) / (111.0 * max(0.1, abs(math.cos(math.radians(lat)))))
    south, north = lat - half_lat, lat + half_lat
    west, east = lon - half_lon, lon + half_lon
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


def build_probes(offsets: list[float], filter_types: list[int], *, skip_control: bool) -> list[Probe]:
    """Probe list, newest first, plus UTC and control comparisons.

    The dashboard sends a *naive local* timestamp for the site's timezone, so `now` here is
    `datetime.now()` — same thing this machine would send. The `utc` probe sends the same
    instant expressed in UTC instead: if only that one returns readings, FortyGuard is reading
    `start_time` as UTC and the dashboard should send UTC too.
    """
    now_local = datetime.now().replace(second=0, microsecond=0)
    now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0, tzinfo=None)

    probes: list[Probe] = []
    for filter_type in filter_types:
        for offset in offsets:
            sign = "+" if offset >= 0 else "-"
            magnitude = abs(offset)
            span = f"{magnitude / 24:g}d" if magnitude >= 24 else f"{magnitude:g}h"
            label = "now" if offset == 0 else f"now{sign}{span}"
            probes.append(Probe(label, now_local + timedelta(hours=offset), filter_type))

        if now_utc != now_local:
            probes.append(Probe("now (as UTC)", now_utc, filter_type))
        if not skip_control:
            probes.append(Probe("control 2024-07-15 14:00", CONTROL_WHEN, filter_type))

    return probes


def report(probes: list[Probe], out_dir: Path) -> None:
    """Print the table, the numeric census for the first payload that had any, and the verdict."""
    print("\n" + "=" * 96)
    print(f"{'probe':<26} {'requested':<17} {'ft':<3} result")
    print("-" * 96)
    for probe in probes:
        print(f"{probe.label:<26} {probe.when:%Y-%m-%d %H:%M}  {probe.filter_type:<3} {probe.verdict}")
    print("=" * 96)

    interesting = next((p for p in probes if p.census_count), None)
    if interesting is not None:
        print(f"\nNumbers in {interesting.label}'s payload, by JSON path "
              f"(parser found {interesting.parsed_count}):\n")
        ranked = sorted(interesting.census.items(), key=lambda kv: len(kv[1]), reverse=True)
        for path, values in ranked[:12]:
            print(f"  {len(values):>7} x  {path:<52} {min(values):>7.2f} .. {max(values):>7.2f}")
        print(f"\n  top level: {_describe(interesting.raw)}")

    with_data = [p for p in probes if p.parsed_count]
    missed = [p for p in probes if not p.parsed_count and p.census_count]

    print("\nVerdict:")
    if with_data:
        freshest = with_data[0]
        print(f"  Parser works. Freshest timestamp with readings: {freshest.label} "
              f"({freshest.when:%Y-%m-%d %H:%M}), peak {freshest.summary['peak_temperature']} C.")
        print(f"  Set the backend's step-back budget to cover that gap "
              f"(NOW_FALLBACK_* in backend/.env).")
    if missed:
        print(f"  Parser is the problem for {len(missed)} probe(s): FortyGuard returned numbers "
              f"but app/services/heatmap.py found none.")
        print(f"  Send the JSON path table above (or the saved file) back to fix the parser.")
    if not with_data and not missed:
        print("  Every probe came back with no numbers at all — the data genuinely is not there "
              "for this AOI at these times, or the AOI is outside FortyGuard's US coverage.")

    print(f"\nRaw payloads saved under {out_dir}/ — nothing in them is secret.")


def save(probes: list[Probe], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for probe in probes:
        if probe.raw is None and probe.error is None:
            continue
        slug = probe.label.replace(" ", "_").replace("(", "").replace(")", "").replace(":", "")
        path = out_dir / f"{slug}_ft{probe.filter_type}.json"
        path.write_text(
            json.dumps(
                {
                    "label": probe.label,
                    "requested": probe.when.isoformat(),
                    "filter_type": probe.filter_type,
                    "error": probe.error,
                    "parsed_summary": probe.summary,
                    "raw_result": probe.raw,
                },
                indent=2,
                default=str,
            )
        )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offsets", default=",".join(f"{o:g}" for o in DEFAULT_OFFSETS_HOURS),
                        help="Comma-separated hour offsets from now; 'd' suffix means days.")
    parser.add_argument("--filter-types", default="1", help="Comma-separated filter_type values to try.")
    parser.add_argument("--lat", type=float, help="AOI centre latitude (default: the demo Manhattan box).")
    parser.add_argument("--lon", type=float, help="AOI centre longitude.")
    parser.add_argument("--size-km", type=float, default=1.5, help="AOI box side length with --lat/--lon.")
    parser.add_argument("--granularity", type=int, default=100, help="FortyGuard grid granularity.")
    parser.add_argument("--concurrency", type=int, default=3, help="Heatmap jobs in flight at once.")
    parser.add_argument("--no-control", action="store_true", help="Skip the 2024-07-15 control probe.")
    parser.add_argument("--out", default="tmp/fortyguard-probe", help="Directory for the raw payloads.")
    args = parser.parse_args()

    settings = Settings()
    if not settings.fortyguard_api_key:
        print("FORTYGUARD_API_KEY is empty. Run this from backend/ so it picks up backend/.env.",
              file=sys.stderr)
        return 2

    ring = DEMO_RING if args.lat is None or args.lon is None else box_around(args.lat, args.lon, args.size_km)
    probes = build_probes(parse_offsets(args.offsets),
                          [int(f) for f in args.filter_types.split(",") if f.strip()],
                          skip_control=args.no_control)

    print(f"endpoint    {settings.fortyguard_base_url}")
    print(f"key         set ({len(settings.fortyguard_api_key)} chars)")
    print(f"AOI         {ring[0]} .. {ring[2]}")
    print(f"probes      {len(probes)}, {args.concurrency} at a time\n")

    gate = asyncio.Semaphore(max(1, args.concurrency))
    done = await asyncio.gather(
        *(run_probe(p, ring, settings, args.granularity, gate) for p in probes)
    )

    out_dir = Path(args.out)
    save(list(done), out_dir)
    report(list(done), out_dir)
    return 0 if any(p.parsed_count for p in done) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
