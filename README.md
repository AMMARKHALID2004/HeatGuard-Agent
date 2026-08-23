# HeatGuard Agent

An autonomous heat-risk agent for outdoor work crews, built for FortyGuard Hackathon '26
(AI Agents + Dashboards tracks).

It reads FortyGuard's hyperlocal temperature data for a site and a work window, reasons
about the risk against fixed thresholds, and returns an actionable call —
**PROCEED / MODIFY / RESCHEDULE** — with plain-language guidance, surfaced on a live
dashboard and pushed to Slack when a shift needs to move.

See [CLAUDE.md](CLAUDE.md) for the full architecture and design constraints.

## Repo layout

| Path | What it is |
| ---- | ---------- |
| [backend/](backend) | FastAPI orchestrator — the agent itself. Owns every credential. Managed with [uv](https://docs.astral.sh/uv/). |
| [frontend/](frontend) | Next.js App Router + Tailwind dashboard, deployed on Vercel. |
| [n8n/](n8n) | The validated prototype workflow — and the source of truth for FortyGuard's request/response shapes. |

## Quickstart

Two terminals.

**Backend** (needs `FORTYGUARD_API_KEY` and `GROQ_API_KEY`):

```bash
cd backend && uv sync && cp .env.example .env
```

Fill in `backend/.env`, then start it:

```bash
cd backend && uv run uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend && npm install && cp .env.example .env.local && npm run dev
```

The dashboard is at http://localhost:3000, the API docs at http://localhost:8000/docs.
`GET /health` reports which credentials the backend found without revealing them.

## How one evaluation works

1. The dashboard `POST`s `{ polygon_aoi, date_time }` to `/api/evaluate` — on button click,
   never on a timer, so development does not burn FortyGuard credits.
2. The backend translates that into FortyGuard's actual request shape (a GeoJSON
   FeatureCollection plus a split `date_time` object), submits a heatmap job, and polls it
   with a **bounded** retry count and exponential backoff — returning a 504 rather than
   spinning forever.
3. The heatmap is reduced to peak / average / sample temperatures **in Python**.
4. Groq (`llama-3.3-70b-versatile`) writes the recommendation and reasoning.
5. **The thresholds are code, not prompt:** `risk_level` and `decision` are re-derived
   server-side from the peak temperature, so a hallucinated classification cannot ship.
6. A `RESCHEDULE` decision also posts to the Slack Incoming Webhook, best-effort.

Risk thresholds (peak temperature): **LOW** < 30 °C → PROCEED · **MEDIUM** 30–33 °C →
MODIFY · **HIGH** ≥ 33 °C → RESCHEDULE.

## The contract between backend and frontend

`backend/app/schemas.py` and `frontend/lib/types.ts` describe the same shape. Change one,
change the other.

```jsonc
{
  "risk_level": "HIGH",              // LOW | MEDIUM | HIGH
  "peak_temperature": 41.2,          // null when the heatmap had no usable readings
  "average_temperature": 38.4,       // null likewise
  "decision": "RESCHEDULE",          // PROCEED | MODIFY | RESCHEDULE
  "recommendation": "…",             // what the supervisor should do
  "reason": "…",                     // the numbers and the threshold crossed
  "activity_id": "…",                // FortyGuard job id, for tracing
  "evaluated_at": "2026-08-23T09:15:00Z",
  "alert_sent": true                 // whether Slack actually accepted the alert
}
```

The agent returns `null` for unavailable data rather than inventing a value — the frontend
renders `—`.

## Secrets

`FORTYGUARD_API_KEY`, `GROQ_API_KEY`, and `SLACK_WEBHOOK_URL` live only in
`backend/.env`. Nothing secret belongs in `frontend/`, where every `NEXT_PUBLIC_*` value is
visible in the browser. `.gitignore` excludes `.env` files and keeps the `.env.example`
templates.
