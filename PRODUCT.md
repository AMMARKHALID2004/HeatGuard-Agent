# HeatGuard Agent — Product Context

## What this is
An autonomous AI agent built for FortyGuard Hackathon'26 (AI Agents + Dashboards tracks). It polls FortyGuard's hyperlocal Temperature API for a defined area, uses an LLM to reason about heat risk against fixed thresholds, and produces an actionable decision (PROCEED / MODIFY / RESCHEDULE) with a plain-language recommendation, delivered via Slack and displayed on a live dashboard.

## Target users
- Construction site supervisors and safety officers who need quick go/no-go decisions for outdoor shifts
- Hackathon judges evaluating the AI Agents + Dashboards tracks
- Demo scenario: outdoor construction site heat risk assessment

## Core workflow
1. User searches/selects a US location (or uses pre-loaded Lower Manhattan demo)
2. User picks a work window start time (defaults to current hour)
3. User clicks "Run Evaluation"
4. Backend calls FortyGuard async heatmap API for that AOI/time
5. Backend extracts peak/average temps, applies region-specific climate zone thresholds
6. Groq LLM generates recommendation/reasoning (never decides thresholds)
7. Backend returns decision with zone info, temps, activity_id, Slack alert status
8. Dashboard displays decision card, risk-tinted map, history list

## Key differentiators
- **Region-aware thresholds**: Same peak temperature means different risk in Phoenix vs Minneapolis
- **Server-enforced thresholds**: LLM never picks cutoffs; backend `risk.py` is source of truth
- **Transparent zone display**: Decision card shows exactly which climate zone applied and its thresholds
- **Production UX**: No debug panels, no jargon, clear plain-language errors
- **Mock mode**: Full offline development via `USE_MOCK_DATA` (hidden in production)

## Visual identity
- Dark, high-contrast dashboard (slate/near-black backgrounds)
- Risk-level color system: green (LOW), amber (MEDIUM), red (HIGH) — consistent across map, card, history
- Clean typography, tabular figures for temperatures, clear visual hierarchy
- Leaflet dark map tiles (CARTO) with AOI polygon tinted by risk level
- Professional, not "developer tool" — suitable for site supervisor use on tablet/phone

## Technical architecture
- **Backend**: FastAPI (Python 3.11+) on Render/Railway
- **Frontend**: Next.js 14 App Router + Tailwind on Vercel
- **LLM**: Groq free tier, `openai/gpt-oss-120b` (OpenAI-compatible)
- **Temperature data**: FortyGuard API (async submit-and-poll)
- **Geocoding**: OpenStreetMap Nominatim (proxied server-side for User-Agent)
- **Alerts**: Slack Incoming Webhook (only on RESCHEDULE)
- **Testing**: 115 unit/integration tests, mocked transports

## Climate zones (backend source of truth)
| Zone | States (examples) | LOW | MEDIUM | HIGH |
|------|-------------------|-----|--------|------|
| Hot-Humid | FL, TX (Gulf), LA, coastal GA/SC | < 34°C | 34–37°C | ≥ 37°C |
| Hot-Dry | AZ, NV, southern CA, west TX | < 36°C | 36–39°C | ≥ 39°C |
| Mixed-Humid | NY, most eastern/central US | < 30°C | 30–33°C | ≥ 33°C |
| Cold/Northern | MN, ME, WA, MT, ND | < 27°C | 27–30°C | ≥ 30°C |

## Current state
- Backend fully implemented with climate zones, tests passing
- Frontend has dashboard, map, decision card, history, mock mode
- **Missing**: Location search box, zone display on card, shared zone logic, plain-language copy audit
- Demo location hardcoded to Lower Manhattan (pre-tested end-to-end)