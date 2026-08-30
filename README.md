# HeatGuard Agent

An autonomous heat-risk agent for outdoor work crews, built for FortyGuard Hackathon '26
(AI Agents + Dashboards tracks).

It reads FortyGuard's hyperlocal temperature data for a site and a work window, reasons
about the risk against **climate-zone-aware** thresholds, and returns an actionable call —
**PROCEED / MODIFY / RESCHEDULE** — with plain-language guidance, surfaced on a live map
dashboard and pushed to Slack when a shift needs to move.

**Live demo:** https://truthful-clarity-production-b361.up.railway.app/

For deeper design notes, see [`backend/README.md`](backend/README.md) and
[`frontend/AGENTS.md`](frontend/AGENTS.md).

## Repo layout

| Path | What it is |
| ---- | ---------- |
| [backend/](backend) | FastAPI orchestrator — the agent itself. Owns every credential. Managed with [uv](https://docs.astral.sh/uv/). |
| [frontend/](frontend) | Next.js App Router + Tailwind dashboard with a real Leaflet map, deployed on Railway. |
| [n8n/](n8n) | The original prototype workflow — reference only, and the source of truth for FortyGuard's request/response shapes. |

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

Want to work on the UI without spending FortyGuard/Groq credits? Set
`NEXT_PUBLIC_USE_MOCK_DATA=1` in `frontend/.env.local` — every state (PROCEED / MODIFY /
RESCHEDULE, no-readings, rate-limited, timeout, misconfigured) is a click away from the mock
scenario picker, with no network calls. Mock responses are clearly banner-flagged and their
`activity_id` always starts with `mock-` so they can't be mistaken for a real evaluation.

## How one evaluation works

1. The dashboard `POST`s `{ polygon_aoi, date_time, state }` to `/api/evaluate` — on button
   click, never on a timer, so development does not burn FortyGuard credits.
2. The backend resolves the site's **climate zone** from its US state (`app/climate.py`) —
   the same peak temperature is safe in Phoenix and dangerous in Minnesota, so thresholds
   are regional, not one national cutoff.
3. It translates the request into FortyGuard's actual shape (a GeoJSON FeatureCollection
   plus a split `date_time` object), submits a heatmap job, and polls it with a **bounded**
   retry count and exponential backoff — returning a 504 rather than spinning forever.
4. The heatmap is reduced to peak / average / sample temperatures **in Python**.
5. Groq (`openai/gpt-oss-120b`) writes the recommendation and reasoning, given the zone's
   thresholds.
6. **The thresholds are code, not prompt:** `risk_level` and `decision` are re-derived
   server-side from the measured peak and the resolved zone, so a hallucinated
   classification can't ship. A heatmap with no usable readings floors to `MEDIUM`/`MODIFY`
   with `null` temperatures — a green `PROCEED` is a safety claim nothing can back.
7. A `RESCHEDULE` decision also posts to the Slack Incoming Webhook, best-effort.

There's also a separate `GET /api/geocode?q=` endpoint that powers the dashboard's location
search box: it looks up US places (via Nominatim) and tags each suggestion with the climate
zone and thresholds it would use, so you can preview the banding before running an
evaluation.

### Climate-zone thresholds (peak temperature, °C)

| Zone | LOW → PROCEED | MEDIUM → MODIFY | HIGH → RESCHEDULE |
| ---- | -------------- | ---------------- | ------------------ |
| Hot-Humid (Gulf / Southeast) | < 34 | 34–37 | ≥ 37 |
| Hot-Dry (desert Southwest) | < 36 | 36–39 | ≥ 39 |
| Mixed-Humid (default) | < 30 | 30–33 | ≥ 33 |
| Cold / Northern | < 27 | 27–30 | ≥ 30 |

A site's state maps to one of these zones (`STATE_TO_ZONE` in `backend/app/climate.py`);
anywhere unmapped, including the demo's NYC site, falls back to Mixed-Humid.

## The contract between backend and frontend

`backend/app/schemas.py` and `frontend/lib/types.ts` describe the same shape. Change one,
change the other.

```jsonc
{
  "risk_level": "HIGH",              // LOW | MEDIUM | HIGH | UNKNOWN
  "peak_temperature": 41.2,          // null when the heatmap had no usable readings
  "average_temperature": 38.4,       // null likewise
  "decision": "RESCHEDULE",          // PROCEED | MODIFY | RESCHEDULE | NO_DATA
  "recommendation": "…",             // what the supervisor should do
  "reason": "…",                     // the numbers and the threshold crossed
  "climate_zone": {                  // which zone's cutoffs were applied
    "name": "Mixed-Humid",
    "medium_threshold_c": 30,
    "high_threshold_c": 33
  },
  "activity_id": "…",                // FortyGuard job id, for tracing
  "evaluated_at": "2026-08-23T09:15:00Z",
  "alert_sent": true                 // whether Slack actually accepted the alert
}
```

The agent returns `null` for unavailable data rather than inventing a value — the frontend
renders `—`.

## Frontend notes

- The AOI map (`components/AoiMap.tsx` / `MapCanvas.tsx`) is a real Leaflet map, client-only
  rendered (`ssr: false`), tinted by the enforced risk level.
- `SearchLocation.tsx` calls `/api/geocode` so a supervisor can search any US site by name
  instead of only using the fixed demo AOI.
- Shift times account for the site's local timezone via `tz-lookup`.
- History of evaluations is in-memory for the session and resets on reload.

## Secrets

`FORTYGUARD_API_KEY`, `GROQ_API_KEY`, and `SLACK_WEBHOOK_URL` live only in
`backend/.env`. Nothing secret belongs in `frontend/`, where every `NEXT_PUBLIC_*` value is
visible in the browser. `.gitignore` excludes `.env` files and keeps the `.env.example`
templates.

## What doesn't work yet

- **The heatmap parser doesn't yet read the real response shape.** We assumed a `cells`
  list of `{"temperature": ...}` objects (that's what the unit tests mock). A live probe
  (`scripts/probe_fortyguard.py`) against the real API confirms the actual response nests
  per-tile temperatures at `map_data.features[].properties.{average_temperature,
  min_temperature, max_temperature}`, with aggregate stats at
  `stats_data.temperature_stats.{minimum, maximum, mean, standard_deviation}` — see the
  captured example below. `app/services/heatmap.py` doesn't look in either place yet, so
  it currently reports zero readings on every real request, mocked tests notwithstanding.
  This is the next fix, not a hypothetical.
- **Which FortyGuard analysis mode we're hitting is unconfirmed.** FortyGuard's docs
  describe multiple analysis layers (snapshot / exceedance / persistence); we're calling
  `/v1/heatmap` and treating the result as a snapshot of point temperatures, but we haven't
  gotten confirmation from FortyGuard that this is the correct layer for a "is it too hot to
  work right now" decision.
- **No persistence.** Evaluation history lives in frontend memory for the browser session
  only — it resets on page reload or backend restart. There's no database.

## A real FortyGuard API call

Captured live with `cd backend && uv run python scripts/probe_fortyguard.py --offsets "" ` against
the demo AOI (Lower Manhattan) at **2024-07-15, 14:00** — the timestamp validated in the
original n8n prototype.

**Request:** `POST https://api.fortyguard.com/v1/heatmap` (header `api-key: <FORTYGUARD_API_KEY>`)
```json
{
  "polygon_aoi": {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "properties": {},
        "geometry": {
          "type": "Polygon",
          "coordinates": [[
            [-74.017, 40.705], [-74.003, 40.705],
            [-74.003, 40.718], [-74.017, 40.718],
            [-74.017, 40.705]
          ]]
        }
      }
    ]
  },
  "date_time": { "start_date": "2024-07-15", "start_time": "14:00", "filter_type": 1 },
  "granularity": 100
}
```

**Response** (trimmed — the real payload has one `Feature` per grid tile; three shown of many):
```json
{
  "data": {
    "status": "Completed",
    "result": {
      "map_data": {
        "type": "FeatureCollection",
        "features": [
          {
            "id": "129",
            "type": "Feature",
            "properties": {
              "tile_id": 129,
              "average_temperature": 31.8891,
              "min_temperature": 31.8891,
              "max_temperature": 31.8891
            },
            "geometry": { "type": "Polygon", "coordinates": ["... tile boundary ..."] }
          },
          {
            "id": "137",
            "type": "Feature",
            "properties": {
              "tile_id": 137,
              "average_temperature": 33.1396,
              "min_temperature": 33.1396,
              "max_temperature": 33.1396
            },
            "geometry": { "type": "Polygon", "coordinates": ["... tile boundary ..."] }
          }
        ]
      },
      "stats_data": {
        "temperature_stats": {
          "minimum": 31.887,
          "maximum": 33.1424,
          "mean": 32.2552,
          "standard_deviation": 0.4149
        },
        "temperature_frequency": { "x_axis": [32.0, 33.0], "y_axis": [111, 39] }
      }
    }
  }
}
```

Peak 33.14°C / average 32.26°C over this AOI falls in the **Mixed-Humid MEDIUM band**
(30–33°C → `MODIFY`), so this request would drive a real `MODIFY` decision end to end.

This also confirms the schema mismatch flagged above with real numbers instead of an empty
result: temperatures live at `map_data.features[].properties.{average_temperature,
min_temperature, max_temperature}` and `stats_data.temperature_stats.{minimum, maximum,
mean, standard_deviation}` — not the `cells` array the parser and its unit tests currently
assume. `app/services/heatmap.py` needs to read this shape before peak/average
temperatures will ever populate from a real request.
