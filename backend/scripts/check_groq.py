"""Live check: does the Groq half of the agent actually work with your key?

Makes real calls to Groq. Touches no FortyGuard credits — the heatmaps below are synthetic,
so this isolates one credential at a time. Run it from `backend/`:

    uv run python scripts/check_groq.py

It walks one heatmap through each risk band and prints what the agent decided, so you can
see the thresholds firing end to end. Nothing here prints your API key.
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Allow `python scripts/check_groq.py` as well as `python -m scripts.check_groq`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agent import AgentError, HeatRiskAgent  # noqa: E402
from app.config import Settings  # noqa: E402

# Synthetic `data.result` payloads, one per band. Peak drives the classification.
CASES = [
    ("LOW band      (peak 24.0 C)", {"cells": [{"temperature": 22.0}, {"temperature": 24.0}]}),
    ("MEDIUM band   (peak 31.5 C)", {"cells": [{"temperature": 30.0}, {"temperature": 31.5}]}),
    ("HIGH band     (peak 41.2 C)", {"cells": [{"temperature": 38.4}, {"temperature": 41.2}]}),
    ("no readings   (peak null)  ", {"cells": []}),
]

EXPECTED = {
    "LOW band      (peak 24.0 C)": "PROCEED",
    "MEDIUM band   (peak 31.5 C)": "MODIFY",
    "HIGH band     (peak 41.2 C)": "RESCHEDULE",
}


async def main() -> int:
    logging.basicConfig(level=logging.WARNING, format="  ! %(message)s")
    settings = Settings()

    if not settings.groq_api_key:
        print(
            "GROQ_API_KEY is empty.\n\n"
            "  1. Get a key at https://console.groq.com → API Keys → Create API Key\n"
            "  2. Add this line to backend/.env (which is gitignored):\n"
            "       GROQ_API_KEY=your_key_here\n"
            "  3. Re-run this script from the backend/ directory.",
            file=sys.stderr,
        )
        return 2

    if not Path(".env").exists():
        print(
            "Warning: no .env in the current directory. Settings only auto-loads "
            "backend/.env when you run this from backend/.\n",
            file=sys.stderr,
        )

    print(f"model    {settings.groq_model}")
    print(f"endpoint {settings.groq_base_url}")
    print(f"key      set ({len(settings.groq_api_key)} chars)\n")

    when = datetime.now().replace(hour=14, minute=0, second=0, microsecond=0) + timedelta(days=1)
    failures = 0

    async with HeatRiskAgent(settings) as agent:
        for label, heatmap in CASES:
            try:
                decision = await agent.assess(heatmap, date_time=when)
            except AgentError as exc:
                print(f"{label}  ->  FAILED: {exc}\n")
                failures += 1
                continue

            expected = EXPECTED.get(label)
            ok = expected is None or decision.decision == expected
            if not ok:
                failures += 1

            mark = "ok " if ok else "BAD"
            print(
                f"{label}  ->  [{mark}] {decision.risk_level} / {decision.decision}"
                f"  peak={decision.peak_temperature} avg={decision.average_temperature}"
            )
            if expected and not ok:
                print(f"      expected decision {expected}")
            print(f"      reason: {decision.reason}")
            print(f"      recommend: {decision.recommendation}\n")

    if failures:
        print(f"{failures} case(s) failed.")
        return 1

    print("All cases passed — Groq reasoning and threshold enforcement both work.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
