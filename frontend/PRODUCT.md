# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: Construction site supervisor/foreman evaluating heat risk for outdoor crew shifts. They stand on-site or in a site office, need a fast go/no-go decision for the upcoming shift, and need to justify it to the crew and management. Secondary: Safety manager / EHS officer monitoring multiple sites (future).

## Product Purpose

HeatGuard Agent makes it possible to get a single authoritative heat-risk decision (PROCEED / MODIFY / RESCHEDULE) for a specific outdoor work site and shift start time, backed by hyperlocal temperature data from FortyGuard satellite imagery and LLM reasoning against fixed, research-backed climate-zone thresholds — not generic weather-app temperatures or static OSHA heat-index charts. The output includes plain-language recommendation and reasoning the supervisor can defend, plus real-time Slack alerting when RESCHEDULE triggers so the whole crew/office knows immediately.

## Positioning

The only tool that combines FortyGuard's hyperlocal satellite temperature grid with climate-zone-specific mortality-research thresholds and an LLM that outputs a defensible, auditable decision — not a temperature reading, not a risk score, but the call itself.

## Operating Context

- Used on-site (tablet/phone) or in site office (desktop) before shift start
- Workflow: search site location → pick shift start (Now / +3h / +6h / +12h) → press Evaluate → read decision → if RESCHEDULE, Slack alert fires automatically
- FortyGuard API credits are limited; evaluations are button-triggered, not on a timer
- Backend runs on FastAPI (Python); frontend on Next.js (App Router) + Tailwind, deployed on Vercel
- Mock mode (USE_MOCK_DATA) exists for development/demo; hidden in production builds
- Agent output contract is strict JSON: {risk_level, peak_temperature, average_temperature, decision, recommendation, reason, climate_zone, evaluated_at, alert_sent}

## Capabilities and Constraints

- Climate zones: Hot-Humid, Hot-Dry, Mixed-Humid, Cold/Northern — each with fixed thresholds (LOW/MEDIUM/HIGH) derived from heat-mortality research
- AOI: ~500m square ring around searched point, generated client-side
- Time window: up to 12 hours ahead (FortyGuard forecast limit)
- Timezone: site-local (IANA via tz-lookup), displayed as "2:00 PM PDT — San Diego time"
- FortyGuard async submit-and-poll pattern (heatmap jobs); bounded retries with exponential backoff
- Groq free tier (openai/gpt-oss-120b) for reasoning; model ID verified via check_groq.py
- Slack Incoming Webhook for alerts (RESCHEDULE only)
- All API keys server-side only (FORTYGUARD_API_KEY, GROQ_API_KEY, SLACK_WEBHOOK_URL)
- Mock scaffolding must be excluded from production builds entirely (dead code elimination)

## Brand Commitments

Name: HeatGuard Agent. Voice: precise, authoritative, calm — a tool that makes the call so the human doesn't have to guess. No marketing fluff. Color/visual identity not yet established; this redesign will create it.

## Evidence on Hand

- Working backend with 115 tests passing (climate zone resolution, geocoding, agent loop)
- Working frontend with location search (Nominatim), timezone-aware work window, map (Leaflet + CARTO dark), decision card, history list
- Live API tests verified for all 4 climate zones
- Demo location: Lower Manhattan construction site (pre-tested end-to-end)

## Product Principles

1. **Decision over data** — The output is a call (PROCEED/MODIFY/RESCHEDULE), not a chart. Every UI choice serves the decision.
2. **Authority through transparency** — Thresholds are shown, reasoning is shown, climate zone is shown. The supervisor can defend the call.
3. **Field-ready first** — Mobile/tablet usability is not an afterthought; it's where the tool is used.
4. **No hidden state** — Mock mode, loading, error, empty, and historic states are all visible and honest.
5. **Credits are finite** — Every evaluation costs FortyGuard credits; the UI makes each one deliberate.

## Accessibility & Inclusion

WCAG 2.1 AA required. This is a safety tool used in high-stakes go/no-go decisions. All interactive elements keyboard-operable, sufficient contrast, screen-reader labels, no motion that can't be reduced, focus management on dynamic updates.