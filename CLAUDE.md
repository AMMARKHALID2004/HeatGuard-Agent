# HeatGuard Agent — Project Context

## What this is
An autonomous AI agent built for FortyGuard Hackathon'26 (AI Agents + Dashboards tracks).
It polls FortyGuard's hyperlocal Temperature API for a defined area, uses an LLM to reason
about heat risk against fixed thresholds, and produces an actionable decision
(PROCEED / MODIFY / RESCHEDULE) with a plain-language recommendation, delivered via Slack
and displayed on a live dashboard.

## Architecture
- **Backend**: FastAPI (`/backend`), the orchestrator — this replaces n8n as the main
  agent logic. Ports the exact same flow your teammate already validated in n8n:
  1. `POST /api/evaluate` (called by frontend) accepts `{ polygon_aoi, date_time }`
  2. Calls FortyGuard `POST https://api.fortyguard.com/v1/heatmap` with header
     `api-key: <FORTYGUARD_API_KEY>` → gets back `activity_id`
  3. Polls `GET /v1/status/{activity_id}` (async pattern — FortyGuard jobs are not
     synchronous) with a bounded retry count + exponential backoff, until
     `status == "Completed"` or timeout
  4. Sends the resulting heatmap data to Groq (free-tier LLM API, OpenAI-compatible,
     model `openai/gpt-oss-120b` — Groq retired the Llama family, so the
     `llama-3.3-70b-versatile` this originally specified now 404s `model_not_found`)
     with a system prompt enforcing fixed risk
     thresholds — do not let the LLM decide thresholds itself
  5. Parses/validates the LLM's JSON output against a Pydantic schema
  6. Returns the decision to the frontend; if `decision == "RESCHEDULE"`, also POSTs to
     a Slack Incoming Webhook URL (`SLACK_WEBHOOK_URL` env var) for the alert
  - Risk thresholds: LOW < 30°C, MEDIUM 30–33°C, HIGH >= 33°C (peak temperature)
  - Decision mapping: LOW→PROCEED, MEDIUM→MODIFY, HIGH→RESCHEDULE
  - FortyGuard API notes: async submit-and-poll pattern; there are multiple analysis
    layers (snapshot / exceedance / persistence) — confirm with FortyGuard's docs/API key
    dashboard which layer `/v1/heatmap` uses vs. others, since picking the wrong layer for
    the use case gives a confidently wrong answer
- **n8n workflow** (`/n8n/heatguard-workflow.json`): kept as the original prototype /
  fallback. Not the primary submission path anymore, but useful to reference or to demo
  as "we also automated alerting with n8n" if time allows
- **Frontend**: Next.js (App Router) + Tailwind, deployed on Vercel
  - Dashboard shows: risk-zone map, current decision card, reasoning/recommendation text,
    and a history list of past evaluations
  - Calls the FastAPI backend (`NEXT_PUBLIC_API_URL`), not n8n directly
- **Alerts**: Slack Incoming Webhook, called directly from FastAPI (simpler and more
  reliable than routing through n8n for the demo)

## Known issues from the original n8n prototype (informing FastAPI rebuild)
1. AOI polygon and date were hardcoded — FastAPI's `/api/evaluate` must accept these as
   real request parameters
2. Slack channel was a placeholder — use a real Slack Incoming Webhook URL, stored in env,
   never hardcoded
3. The original polling loop had no max retry count — FastAPI's poll loop must have a
   bounded number of attempts and a clear timeout error returned to the frontend
4. LLM reasoning previously used a free OpenRouter model — use Groq's free tier
   (OpenAI-compatible endpoint, `openai/gpt-oss-120b`) instead, for speed and
   reliability during judging, at no cost. Groq's lineup moves: verify the model id with
   `uv run python scripts/check_groq.py`, which lists what the key can actually reach
5. Never expose `FORTYGUARD_API_KEY`, `GROQ_API_KEY`, or `SLACK_WEBHOOK_URL` to the
   frontend — these live only in FastAPI's environment

## Conventions
- Keep all FortyGuard API calls and credentials server-side / in n8n — never expose the
  FortyGuard API key in frontend code
- Agent output is always strict JSON matching:
  `{ risk_level, peak_temperature, average_temperature, decision, recommendation, reason }`
  — frontend should type this shape and handle `null` values gracefully (agent returns
  `null` for unavailable data rather than inventing values)
- Frontend polls/calls the webhook on demand (button-triggered), not on a timer, to avoid
  burning FortyGuard API credits during development
- Favor small, demoable increments over a fully "production" build — this is a hackathon;
  optimize for a clean 90-second live demo over edge-case robustness

## When a command can't be run (blocked network, missing tool, permissions, etc.)
If you hit a command you cannot run yourself — blocked package registry (PyPI/npm),
missing CLI tool, no internet access, permission denied, or any other environment
limitation — **stop immediately at that point**. Do not silently substitute a workaround
(like stubbing imports, mocking the dependency, or skipping the step) and continue on to
later work. Do not wait until the end of the task to mention it.

Instead:
1. Tell me exactly what command failed and why (paste the actual error).
2. Tell me exactly what you need me to run on my end to unblock it (the precise command).
3. Wait for me to confirm I've done it before continuing.

The only exception: read-only verification workarounds (e.g., stubbing an import purely
to sanity-check logic you already wrote) are fine, but you must still flag them
explicitly when you do it, and the real, unstubbed version must still be run and
confirmed working before the task is considered done — not left as a TODO for later.

## Secrets — never commit these
Real API keys and secrets must NEVER be written into code, committed to git, or pushed
to GitHub — not even temporarily, not even in a private repo. This applies to
`FORTYGUARD_API_KEY`, `GROQ_API_KEY`, `SLACK_WEBHOOK_URL`, and anything similar.
- Real values go only in a local `.env` file, which must be listed in `.gitignore`
- Only a `.env.example` (listing variable names with placeholder/empty values, no real
  secrets) is committed, so teammates know what's required
- Before every commit, scan the diff for anything that looks like a real key/token/secret
  and stop to flag it rather than committing it

## End of every session
1. Scan for secrets per the rule above before committing anything.
2. Stage, commit (clear message describing what was done), and push to GitHub.
3. Give me a short summary of: what was completed, what's still pending, and anything
   you need me to do manually before the next session — see below.

## Things only I can do — always ask, never skip silently
Some setup steps require my accounts/credentials and can't be done by you. Whenever a
task needs one of these, stop and ask me to do it (don't guess, don't leave a silent
TODO, don't work around it):
- Creating accounts or generating API keys (FortyGuard, Groq, Slack, Vercel, Render/
  Railway, etc.)
- Pasting real values into my local `.env` file
- Approving billing, OAuth consent screens, or third-party app permissions
- Anything requiring 2FA, email verification, or a browser login
- Confirming a real Slack channel/webhook to use
List exactly what I need to do and why, then wait for me to confirm it's done before
continuing anything that depends on it.

When an API key is needed, don't just name it — walk me through getting it step by step,
since I have no prior experience with APIs:
1. The exact URL to sign up / log in to get the key
2. The exact clicks/menu path once logged in (e.g., "Dashboard → API Keys → Create Key")
3. What to name the key if it asks
4. Exactly which line to add to my local `.env` file, with the correct variable name
   (e.g., `GROQ_API_KEY=paste_your_key_here`)
5. Confirm the `.env` file is in `.gitignore` before I add the real key to it
Do not assume I know any of this — spell out every step, and wait for me to confirm the
key is in place before continuing.

## Ask me to test things myself — only when actually necessary
Don't ask me to test or run things by default, and don't ask for every small step. Verify
what you can yourself first (run the code, run tests, curl the endpoint, check logs) and
only involve me when one of these is true:
- The check requires something only I have access to (my browser session, my Slack, my
  deployed URL, my physical device)
- You've verified it on your end but it depends on an external service/account you can't
  fully confirm from here (e.g., "server starts and returns 200 locally" is yours to
  verify; "Slack message actually arrived in the channel" is mine)
- Something failed after your own attempts and you need my eyes on the actual error/output
- It's a final end-to-end milestone worth a real confirmation before moving on (e.g., full
  demo flow working), not every intermediate step
If you can verify something yourself, just do it and tell me what you checked — don't ask
me to redundantly confirm it too. When you do need me to check something, batch it: don't
ask me to test the same feature piece-by-piece across several messages.

## Demo scenario
Outdoor construction site heat risk. One fixed example location, pre-tested end to end,
used as the primary live demo. Have a backup screen-recorded video in case live APIs are
flaky during judging.
