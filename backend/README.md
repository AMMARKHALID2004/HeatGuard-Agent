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

85 tests, no network. Every suite drives the *real* client code against scripted replies via
`httpx.MockTransport`, so nothing of ours is stubbed and no request leaves the machine:

- `tests/test_fortyguard.py` — `FortyGuardClient`: the success path (including the exact
  request body sent upstream), the bounded-poll timeout, and the API-error cases.
- `tests/test_agent.py` — `HeatRiskAgent`. The mock transport is injected into a real
  `AsyncOpenAI` client (`http_client=`), so the SDK's own serialization, auth header, and
  envelope parsing all execute. Covers the request Groq actually receives, threshold
  enforcement over a hallucinated go-ahead, prose that would contradict the enforced verdict,
  the unmeasurable-area fail-safe, the reasoning deadline, the single repair turn, a 200 that
  is not a chat completion at all, and the API-error paths.
- `tests/test_evaluate.py` — `POST /api/evaluate` through Starlette's `TestClient`. Four of
  these run the *whole* chain with both upstreams behind `MockTransport` — FortyGuard submit,
  poll, Groq completion and Slack post all fire, and the assertions check that neither API key
  reaches the response body. The rest cover the error contract: every failure's status, code
  and `retryable` flag, that all of them share one body shape, that a 422 never spends a
  FortyGuard credit, and that a broken `SLACK_WEBHOOK_URL` costs the alert but not the
  decision.


Stdlib `unittest` only — no test dependency to install.

Do **not** reach for `uv run pytest`: pytest is not a project dependency, so `uv run` falls
back to whatever `pytest` is on `PATH`. Under Anaconda that is a different interpreter
without `fastapi` or `openai` installed, and the suite fails at import with
`ModuleNotFoundError` that looks like broken code rather than the wrong runner. If you want
pytest, add it to the project first (`uv add --dev pytest`) so `uv run` resolves it from
`.venv`; it collects these tests as-is.

### Live check against the real Groq API

The suite above never leaves the machine, so it cannot tell you whether your `GROQ_API_KEY`
actually works. This does:

```bash
cd backend && uv run python scripts/check_groq.py
```

It walks a synthetic heatmap through each risk band and prints the decision, so you see the
thresholds firing end to end. It spends **no FortyGuard credits** — the heatmaps are
hard-coded, which isolates one credential at a time. Exit code 0 means Groq reasoning and
threshold enforcement both work; with no key set it tells you where to get one.

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

### Errors the dashboard can display

Every non-2xx response — 422 included — has the same body, so the frontend has one shape to
parse and never has to assemble its own wording:

```json
{
  "detail": "The temperature service is still working on this area and did not finish in time. Nothing is wrong with the request — try again in a moment.",
  "error": {
    "code": "fortyguard_timeout",
    "message": "The temperature service is still working on this area and did not finish in time. Nothing is wrong with the request — try again in a moment.",
    "hint": "FortyGuard heatmap jobs are asynchronous. Raise POLL_MAX_ATTEMPTS in backend/.env if large areas routinely need longer.",
    "retryable": true
  }
}
```

`detail` duplicates `error.message` so a client reading only FastAPI's default field still
shows a readable sentence. `retryable` is the field worth branching on: it separates "press
the button again and it may work" from "it will fail the same way until someone fixes
something".

| Status | `code` | Retryable | Cause |
| ------ | ------ | --------- | ----- |
| 422 | `invalid_request` | no | AOI ring or `date_time` failed validation |
| 500 | `fortyguard_not_configured` | no | No `FORTYGUARD_API_KEY`, or a malformed `FORTYGUARD_BASE_URL` |
| 500 | `agent_not_configured` | no | No `GROQ_API_KEY` |
| 502 | `fortyguard_failed` | no | FortyGuard rejected the request |
| 502 | `fortyguard_unreachable` | yes | Network error reaching FortyGuard |
| 502 | `agent_failed` | yes | Groq returned something unusable twice — including a 200 that is not a chat completion |
| 503 | `agent_rate_limited` | yes | Groq's free tier limit; carries `Retry-After` when Groq sent one |
| 504 | `fortyguard_timeout` | yes | Heatmap job outlasted the bounded poll budget, or the connection timed out |
| 504 | `agent_timeout` | yes | Reasoning outlasted `AGENT_DEADLINE_SECONDS` |

**Upstream error text is never in the response.** `FortyGuardError` embeds up to 300
characters of FortyGuard's reply and `AgentError` embeds Groq's, and an upstream that echoes a
rejected request back would put an API key in a browser payload. The real cause is logged to
the uvicorn console under the same `code` the client saw, so a screenshot of the dashboard is
enough to find the matching log line. `hint` is written per code in `app/errors.py` and quotes
nothing an upstream sent.

A successful response never means "trust the model": `risk_level` and `decision` are always
re-derived in code, a heatmap with no readable temperatures returns MEDIUM/MODIFY with
`null` temperatures rather than a `PROCEED` the data cannot support, and any prose that
argued for a different verdict is replaced along with it.


## Layout

```
app/
├── main.py               FastAPI app, CORS, /health
├── config.py             env-backed Settings
├── schemas.py            request/response contracts
├── errors.py             internal failures -> displayable HTTP responses
├── risk.py               fixed thresholds + decision mapping (not the LLM's call)
├── agent.py              HeatRiskAgent: measure -> reason on Groq -> validate -> threshold
├── routers/evaluate.py   POST /api/evaluate
└── services/
    ├── fortyguard.py     FortyGuardClient: request translation, submit + bounded poll
    ├── heatmap.py        data.result -> peak/average summary
    └── slack.py          RESCHEDULE alert (best-effort)
tests/
├── test_fortyguard.py    FortyGuardClient against httpx.MockTransport
├── test_agent.py         HeatRiskAgent against a MockTransport-backed AsyncOpenAI
└── test_evaluate.py      the route end to end, plus the error contract
scripts/
└── check_groq.py         live Groq call, no FortyGuard credits spent
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
- **The numbers are measured, not generated.** `agent.py` also overwrites
  `peak_temperature` and `average_temperature` with what `heatmap.summarize_heatmap`
  computed, logging a warning on any mismatch. Together with the line above, a model that
  invents a temperature or talks itself into a go-ahead at 41 °C cannot reach the
  dashboard — the model is left responsible only for `recommendation` and `reason`.
- **The guidance never argues against the verdict.** `recommendation` and `reason` are the
  model's to write, and are kept verbatim — but they are printed directly on the dashboard
  card and inside the Slack alert, so when a threshold override contradicts the band the
  model reasoned to, its prose is replaced with `risk.recommendation_for` /
  `risk.reason_for`. "No special heat precautions needed" under a RESCHEDULE header is worse
  than no advice at all.
- **Reasoning runs on Groq through the `openai` SDK.** `AsyncOpenAI` pointed at
  `groq_base_url` (OpenAI-compatible), model `groq_model`, JSON mode, temperature 0.2.
  A reply that is not valid JSON or does not fit `AgentDecision` gets exactly one repair
  turn quoting the validation error back to the model; a second failure raises `AgentError`
  → 502. Transport-level 429s and 5xx are retried inside the SDK (`SDK_MAX_RETRIES`), which
  matters on Groq's rate-limited free tier; an HTTP error is never mistaken for a schema
  error and never earns a repair turn. Neither is a 200 that is not a chat completion at all:
  the SDK builds its response models without validating them, so a mistyped `GROQ_BASE_URL`
  or a proxy's own 200 page arrives as a bare string, and `AgentError` names it instead of
  letting an `AttributeError` become a 500.
- **Python does the arithmetic.** `services/heatmap.py` computes peak and average, unlike
  the prototype, which stringified the whole heatmap into the prompt and let the model find
  the maximum itself.
- **Polling is bounded.** `POLL_MAX_ATTEMPTS` attempts (15) with exponential backoff capped
  at `POLL_MAX_DELAY_SECONDS`, then `FortyGuardTimeout` → 504. That exception subclasses both
  `FortyGuardError` and the builtin `TimeoutError`, so callers can catch either. The
  prototype's unbounded `If → Wait → Check` cycle is the bug this replaces.
- **The clients are injectable.** `async with FortyGuardClient(settings)` owns and closes its
  own `httpx.AsyncClient`; passing `http_client=` supplies your own instead and leaves
  closing to you. `HeatRiskAgent` follows the same shape with `client=` for its
  `AsyncOpenAI`. Those seams are what the tests hang `MockTransport` on.
- **Missing data never becomes a go-ahead.** No readings in the heatmap means `null`
  temperatures, not a guess — and because `PROCEED` is a safety claim that nothing can then
  back, an unmeasurable area floors to MEDIUM/MODIFY with a deterministic `reason`, rather
  than inheriting whatever the model guessed. This matters more than it looks: the
  `TODO(fortyguard-docs)` in `services/heatmap.py` means "parser found zero readings" is a
  live possibility, and the alternative is a green card on a 41 °C site.
- **Reasoning is bounded in wall-clock, not just per request.** `agent_deadline_seconds`
  (45s) caps the entire Groq phase — both schema attempts and every SDK backoff sleep inside
  them — then raises `AgentTimeout` → 504. A per-request timeout is not enough, because
  `MAX_ATTEMPTS` multiplies it and Groq's free tier can send a `Retry-After` far longer than
  the request itself. When Groq says so explicitly, `AgentRateLimited` carries that
  `Retry-After` through to the client as a 503, so the dashboard can time its own retry
  instead of guessing.
- **Failures are translated once, in one place.** `app/errors.py` maps each internal
  exception onto its status, `code`, displayable `message` and `hint`, and is the only place
  the internal cause is logged. The mapping is ordered most-specific-first because the
  hierarchies overlap — `FortyGuardTimeout` is a `FortyGuardError`, and `AgentTimeout` /
  `AgentRateLimited` / `AgentNotConfigured` are all `AgentError`. Anything it does not
  recognise is re-raised rather than flattened, so a genuine bug still surfaces as a 500 with
  a traceback instead of a misleading 502.
- **Slack is best-effort.** A webhook failure is logged and surfaced as
  `alert_sent: false`; the evaluation still succeeds. The `except` around it is deliberately
  broad, because `httpx.InvalidURL` does *not* inherit from `httpx.HTTPError`: a
  `SLACK_WEBHOOK_URL` with a typo'd port escaped a narrower handler and took a valid
  RESCHEDULE down with it — the one verdict that matters most, lost because a *notification*
  was misconfigured.
