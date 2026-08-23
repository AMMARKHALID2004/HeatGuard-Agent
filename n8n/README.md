# n8n — original prototype (reference only)

[`heatguard-workflow.json`](heatguard-workflow.json) is the first working version of
HeatGuard: 16 nodes that validated the flow end to end (FortyGuard submit → poll → LLM
reasoning → Slack). `/backend` is a port of this flow to FastAPI.

**This is reference and fallback, not the submission path.** Its real value is as the
source of truth for what FortyGuard actually accepts and returns — the FastAPI client is
built from the shapes recorded here.

## The flow

```
Execute workflow (manual trigger)
  └─> HTTP Request ............... POST /v1/heatmap
        └─> Check Heatmap Status .. GET /v1/status/{{ $json.data.activity_id }}
              └─> If ............. $json.data.status == "Completed"
                    ├─ false ─> Wait ─> Check Heatmap Status   (loop, no attempt counter)
                    └─ true  ─> Edit Fields ................... heatmap_data = $json.data.result
                          └─> Prepare Heat Data (Code)
                                └─> HeatGuard Agent <── OpenRouter Chat Model
                                      └─> Parse Agent Decision (Code)
                                            └─> Edit Fields1 ─> If1 ($json.decision == "RESCHEDULE")
                                                  ├─ true  ─> Send a message   ("HeatGuard Alert")
                                                  └─ false ─> Send a message1  ("HeatGuard Update")

HeatGuard Webhook (POST /heatguard) ... orphaned, zero connections
```

## What this told us about the FortyGuard API

The `/backend` client is built from these shapes. **Request body** (`HTTP Request` node):

```json
{
  "polygon_aoi": {
    "type": "FeatureCollection",
    "features": [{
      "type": "Feature",
      "properties": {},
      "geometry": { "type": "Polygon", "coordinates": [[[-74.0170, 40.7050], "…"]] }
    }]
  },
  "date_time": { "start_date": "2024-07-15", "start_time": "14:00", "filter_type": 1 },
  "granularity": 100
}
```

So `polygon_aoi` is a **GeoJSON FeatureCollection**, not a bare coordinate ring, and
`date_time` is an **object with split date/time plus `filter_type`** — not an ISO string.
`granularity` sits at the top level.

**Responses are wrapped in a `data` envelope**, per the node expressions:

| Expression | Meaning |
| ---------- | ------- |
| `$json.data.activity_id` | job id returned by `POST /v1/heatmap` |
| `$json.data.status` | poll status, compared against the exact string `"Completed"` |
| `$json.data.result` | the heatmap itself |

Still unconfirmed: the **inner shape of `data.result`**, and what **`filter_type: 1`**
selects (likely the snapshot / exceedance / persistence layer). The export contains no
`pinData`, so it carries no recorded response to answer either. Both are marked
`TODO(fortyguard-docs)` in `backend/app/services/`.

## Known gaps in the prototype

These are the reasons for the FastAPI rebuild. All four are visible in this export and
fixed in `/backend`:

1. **Hardcoded AOI and date** — the NYC polygon and `2024-07-15 14:00` are literals in the
   `HTTP Request` node body. `POST /api/evaluate` takes them as real parameters.
2. **Placeholder Slack channel** — both Slack nodes target `channelId: "123"`. The backend
   uses a real Incoming Webhook from `SLACK_WEBHOOK_URL`.
3. **Unbounded poll loop** — `If → Wait → Check Heatmap Status` has no attempt counter and
   no timeout, so a stuck job loops forever. The backend caps attempts and returns 504.
4. **OpenRouter for reasoning** — the `OpenRouter Chat Model` node is replaced by Groq
   (`llama-3.3-70b-versatile`) for speed and free-tier reliability during judging.

Two more worth knowing:

5. **The LLM did the arithmetic.** `Prepare Heat Data` passed the whole heatmap into the
   prompt (`JSON.stringify($json.heatmap_data)`) and asked the model to find the maximum
   itself. The backend computes peak/average in Python and only lets the model write the
   prose — and re-derives the risk level from the thresholds afterwards.
6. **The webhook was never wired.** `HeatGuard Webhook` has zero connections, and its
   `responseMode` is `responseNode` with no matching *Respond to Webhook* node. The
   workflow only ever ran from the manual trigger.

## Divergences in the FastAPI port (intentional)

- **Slack fires only on `RESCHEDULE`.** The prototype alerted on both branches of `If1`
  ("HeatGuard Alert" vs. "HeatGuard Update"). CLAUDE.md specifies alerting only when a
  shift must move, so the backend does that and reports `alert_sent` in the response.
- **Slack transport is an Incoming Webhook**, not the Slack OAuth node.

## Credentials

Safe to commit as-is: the export references credentials by name and id only
(`Header Auth account 4`, `Slack account`) — no key values, tokens, or webhook URLs are
inlined. Verified by scanning for `xox*`, `hooks.slack.com/services/*`, `sk-*`, and bearer
tokens.

**Re-scan before committing any future export.** n8n can inline header values that were
typed directly into an HTTP Request node rather than stored as a credential.

## Importing it back

n8n → **Workflows** → **Import from File**. Recreate the FortyGuard header-auth and Slack
credentials locally; do not commit them.
