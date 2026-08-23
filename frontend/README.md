# HeatGuard Agent — frontend

Next.js (App Router) + TypeScript + Tailwind v4 dashboard. Talks only to the FastAPI
backend; it never sees the FortyGuard, Groq, or Slack credentials.

## Setup

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_URL, defaults to http://localhost:8000
npm run dev
```

Open http://localhost:3000. The backend must be running (`uvicorn app.main:app --port 8000`)
for the **Evaluate site** button to work.

## Layout

```
app/
├── layout.tsx            root shell + metadata
├── page.tsx              the dashboard (client component, button-triggered)
└── globals.css           Tailwind entry + risk color theme
components/
├── DecisionCard.tsx      current decision, temperatures, recommendation, reasoning
├── AoiMap.tsx            AOI outline tinted by risk (SVG, no map dependency yet)
└── HistoryList.tsx       past evaluations from this session
lib/
├── types.ts              mirrors backend/app/schemas.py
├── api.ts                POST /api/evaluate + FastAPI error handling
├── risk.ts               risk -> style/label mapping, formatters
└── demo.ts               the fixed demo AOI and default work window
```

## Notes

- **Evaluation is button-triggered, never on a timer** — a polling dashboard would burn
  FortyGuard credits during development.
- **`lib/types.ts` mirrors the backend schema.** Change one, change the other.
  `peak_temperature` / `average_temperature` are `number | null`: the agent reports missing
  data rather than inventing values, and the UI renders `—` for it.
- **History is in-memory** and resets on reload. Persisting it needs a store the backend
  owns; out of scope for the demo.
- **`AoiMap` is not a real basemap yet.** It normalizes the AOI ring into an SVG viewBox so
  the dashboard is demoable with zero dependencies — see the TODO in that file for the
  MapLibre/Leaflet upgrade path.

## Deploy (Vercel)

Set the project root to `frontend/`, and set `NEXT_PUBLIC_API_URL` to the deployed backend
URL. The backend's `CORS_ALLOW_ORIGINS` must include the Vercel origin.
