"""Live check: does the Groq half of the agent actually work with your key?

Makes real calls to Groq. Touches no FortyGuard credits — the heatmaps below are synthetic,
so this isolates one credential at a time. Run it from `backend/`:

    uv run python scripts/check_groq.py

It walks one heatmap through each risk band and prints what the agent decided, so you can
see the thresholds firing end to end. Nothing here prints your API key.

Exit codes: 0 all cases passed, 1 a case gave the wrong decision, 2 no key configured,
3 the configuration is wrong — in which case it asks Groq which models your key can reach
and prints the `.env` line that would fix it. Groq's lineup changes, so a model id that
worked last month can start returning `model_not_found`.
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Allow `python scripts/check_groq.py` as well as `python -m scripts.check_groq`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import AsyncOpenAI, OpenAIError  # noqa: E402

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

# Failures that are about the configuration, not the case: every case sends the same request
# shape, so repeating these three more times only buries the message.
_CONFIG_FAULTS = ("model_not_found", "does not exist", "401", "invalid_api_key", "not a chat")

# Model ids that are not chat models at all, whatever else the key can reach.
_NOT_CHAT = ("whisper", "tts", "orpheus", "guard", "embed", "moderation", "safeguard")

# Preferred order among whatever is reachable, biased toward the largest production chat
# model since its prose is what the demo shows. Hints, not a fixed list — Groq's lineup moves,
# which is exactly how the original `llama-3.3-70b-versatile` default stopped working.
_PREFERENCE = ("gpt-oss-120b", "gpt-oss-20b", "70b", "instruct", "versatile")


async def reachable_chat_models(settings: Settings) -> list[str]:
    """Ask Groq which models this key can actually use. Authoritative, unlike the docs."""
    client = AsyncOpenAI(
        api_key=settings.groq_api_key,
        base_url=settings.groq_base_url,
        timeout=settings.http_timeout_seconds,
        max_retries=1,
    )
    try:
        page = await client.models.list()
    finally:
        await client.close()
    ids = sorted(model.id for model in page.data)
    return [i for i in ids if not any(bad in i.lower() for bad in _NOT_CHAT)]


def suggest(models: list[str]) -> str | None:
    for hint in _PREFERENCE:
        for model in models:
            if hint in model:
                return model
    return models[0] if models else None


async def diagnose(settings: Settings) -> None:
    """Print what the key can reach, and the exact line that would fix `.env`.

    On stdout, not stderr: this is part of the report, and the two streams interleave out of
    order the moment anyone pipes the output.
    """
    print("Asking Groq what your key can actually use...\n")
    try:
        models = await reachable_chat_models(settings)
    except OpenAIError as exc:
        print(f"  Could not list models either: {exc}")
        print("  If that was a 401 the key itself is wrong — generate a new one at "
              "https://console.groq.com -> API Keys.")
        return

    if not models:
        print("  Groq listed no chat models for this key. Check its permissions at "
              "https://console.groq.com -> API Keys.")
        return

    print("  Chat models available to you:")
    for model in models:
        print(f"    {model}")

    pick = suggest(models)
    if pick and pick != settings.groq_model:
        print(f"\n  Fix: add this line to backend/.env, then re-run this script.")
        print(f"    GROQ_MODEL={pick}")
    elif pick:
        # Worth saying out loud: the model is fine, so the fault is elsewhere — a bad
        # GROQ_BASE_URL, or a model that is listed but not enabled for chat completions.
        print(f"\n  {settings.groq_model} is in that list, so the model id is not the "
              f"problem. Check GROQ_BASE_URL (currently {settings.groq_base_url}) and the "
              f"error text above.")


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
    config_fault = False

    async with HeatRiskAgent(settings) as agent:
        for label, heatmap in CASES:
            try:
                decision = await agent.assess(heatmap, date_time=when)
            except AgentError as exc:
                print(f"{label}  ->  FAILED: {exc}\n")
                failures += 1
                message = str(exc).lower()
                if any(fault in message for fault in _CONFIG_FAULTS):
                    # Same request shape every case, so the other three would fail the same
                    # way. Stop and diagnose instead of printing this four times.
                    config_fault = True
                    break
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

    if config_fault:
        await diagnose(settings)
        return 3

    if failures:
        print(f"{failures} case(s) failed.")
        return 1

    print("All cases passed — Groq reasoning and threshold enforcement both work.")
    return 0



if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
