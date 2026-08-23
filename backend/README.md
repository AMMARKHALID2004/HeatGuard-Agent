# HeatGuard Agent — backend

FastAPI orchestrator for the heat-risk agent. See `../CLAUDE.md` for the full
architecture; this file covers running it. Dependencies are managed with
[uv](https://docs.astral.sh/uv/).

## Setup

```bash
cd backend && uv sync && cp .env.example .env
```

`uv sync` creates `.venv/`, resolves the dependencies, and writes `uv.lock` (commit the
lockfile). Then fill in `FORTYGUARD_API_KEY` and `GROQ_API_KEY` in `.env`.

## Run

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
```

`uv run` uses the project environment, so there is no venv to activate.

- Interactive docs: http://localhost:8000/docs
- Health + credential check: http://localhost:8000/health

Common uv commands:

| Task | Command |
| ---- | ------- |
| Add a dependency | `uv add <package>` |
| Add a dev-only dependency | `uv add --dev <package>` |
| Remove one | `uv remove <package>` |
| Re-lock after editing `pyproject.toml` | `uv lock` |
| Install exactly the lockfile (CI) | `uv sync --frozen` |
| One-off command in the env | `uv run python -c "…"` |

## Test

```bash
cd backend && uv run python -m unittest discover -v
```

`tests/test_fortyguard.py` drives the real `FortyGuardClient` against scripted responses
via `httpx.MockTransport`, covering the success path (including the exact request body sent
upstream), the bounded-poll timeout, and the API-error cases. It uses only the stdlib
`unittest` — no test dependency to install — and pytest will collect it as-is if you add
one later.

## The one endpoint that matters

`POST /api/evaluate`

```json
{
  "polygon_aoi": [[-74.017, 40.705], [-74.003, 40.705], [-74.003, 40.718], [-74.017, 40.718], [-74.017, 40.705]],
  "date_time": "2024-07-15T14:00:00"
}
```

`filter_type` (default 1) and `granularity` (default 100) are optional overrides.

Returns the agent decision:

```json
{
  "risk_level": "HIGH",
  "peak_temperature": 41.2,
  "average_temperature": 38.4,
  "decision": "RESCHEDULE",
  "recommendation": "…",
  "reason": "…",
  "activity_id": "…",
  "evaluated_at": "2026-08-23T09:15:00Z",
  "alert_sent": true
}
```

Error mapping — the dashboard can rely on these:

| Status | Meaning |
| ------ | ------- |
| 422 | AOI ring or `date_time` failed validation |
| 502 | FortyGuard or Groq rejected the call / returned something unusable |
| 504 | FortyGuard job did not finish inside the bounded poll budget |

## Layout

```
app/
├── main.py               FastAPI app, CORS, /health
├── config.py             env-backed Settings
├── schemas.py            request/response contracts
├── risk.py               fixed thresholds + decision mapping (not the LLM's call)
├── routers/evaluate.py   POST /api/evaluate
└── services/
    ├── fortyguard.py     FortyGuardClient: request translation, submit + bounded poll
    ├── heatmap.py        data.result -> peak/average summary
    ├── llm.py            Groq reasoning, schema-validated
    └── slack.py          RESCHEDULE alert (best-effort)
tests/
└── test_fortyguard.py    FortyGuardClient against httpx.MockTransport
```

## Design notes

- **The public API is not FortyGuard's API.** `/api/evaluate` takes a plain
  `[[lon, lat], …]` ring and an ISO timestamp. `services/fortyguard.py` translates that
  into the GeoJSON FeatureCollection and split `date_time` object FortyGuard actually
  wants, and unwraps the `data` envelope it returns. Those shapes come from the validated
  prototype — see `../n8n/README.md`.
- **Thresholds are code, not prompt.** The prompt states LOW/MEDIUM/HIGH so the model's
  prose stays consistent, but `risk.enforce_thresholds` overwrites `risk_level` and
  `decision` from the peak temperature after the model replies.
- **Python does the arithmetic.** `services/heatmap.py` computes peak and average, unlike
  the prototype, which stringified the whole heatmap into the prompt and let the model find
  the maximum itself.
- **Polling is bounded.** `POLL_MAX_ATTEMPTS` attempts (15) with exponential backoff capped
  at `POLL_MAX_DELAY_SECONDS`, then `FortyGuardTimeout` → 504. That exception subclasses both
  `FortyGuardError` and the builtin `TimeoutError`, so callers can catch either. The
  prototype's unbounded `If → Wait → Check` cycle is the bug this replaces.
- **The client is injectable.** `async with FortyGuardClient(settings)` owns and closes its
  own `httpx.AsyncClient`; passing `http_client=` supplies your own instead and leaves
  closing to you. That seam is what the tests hang `MockTransport` on.
- **Missing data stays missing.** No readings in the heatmap means `null` temperatures,
  not a guess — and with no peak to threshold against, the model's own classification is
  left in place.
- **Slack is best-effort.** A webhook failure is logged and surfaced as
  `alert_sent: false`; the evaluation still succeeds.
