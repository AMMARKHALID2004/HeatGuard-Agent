"""A fake FortyGuard + Groq, for exercising the real backend over real HTTP.

Verification scaffold, not part of the service. It exists so the whole stack — uvicorn,
httpx, the `openai` SDK, the dashboard — can run unmodified while only the two upstream
*servers* are faked. Nothing is stubbed inside the application itself.

    python scripts/stub_upstream.py --port 8210

Then point the backend at it:

    FORTYGUARD_BASE_URL=http://127.0.0.1:8210/v1 \
    GROQ_BASE_URL=http://127.0.0.1:8210/groq/v1 \
    SLACK_WEBHOOK_URL=http://127.0.0.1:8210/slack \
    .venv/bin/python -m uvicorn app.main:app --port 8000

Routes:
    POST /v1/heatmap             -> {"data": {"activity_id": ...}}
    GET  /v1/status/{id}         -> Processing, until told otherwise
    POST /groq/v1/chat/...       -> an OpenAI-shaped reply carrying the agent's JSON
    POST /slack                  -> 200, and prints what it received
    GET  /control/{mode}         -> mode in {complete, never, no-readings}
"""

from __future__ import annotations

import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# What `GET /v1/status/{id}` should do. Flipped at runtime via /control/{mode} so a single
# server can serve the timeout test and the happy path without a restart.
MODE = "complete"

_HOT_CELLS = [
    {"cell_id": i, "temperature": t}
    for i, t in enumerate([38.1, 39.4, 40.2, 41.2, 37.8, 36.9, 38.6, 39.9])
]


def _heatmap_result(mode: str) -> dict:
    # "no-readings" returns a grid the collector deliberately cannot read (stats nested under
    # a temperature key), which is how a null-temperature response is produced for real
    # rather than hand-written. See the note in app/services/heatmap.py.
    if mode == "no-readings":
        return {"summary": {"temperature": {"peak": 41.2, "grid_id": 7}}}
    return {"cells": _HOT_CELLS, "units": "celsius"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args) -> None:
        print(f"  stub: {fmt % args}", flush=True)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's casing
        global MODE

        control = re.fullmatch(r"/control/(complete|never|no-readings)", self.path)
        if control:
            MODE = control.group(1)
            print(f"  stub: MODE -> {MODE}", flush=True)
            self._send({"mode": MODE})
            return

        if self.path.startswith("/v1/status/"):
            if MODE == "never":
                self._send({"data": {"status": "Processing"}})
                return
            self._send({"data": {"status": "Completed", "result": _heatmap_result(MODE)}})
            return

        self._send({"error": f"no stub route for GET {self.path}"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""

        if self.path.startswith("/v1/heatmap"):
            # Echoing the key back would risk logging a real one; just confirm it arrived.
            print(f"  stub: heatmap submit, api-key header present={bool(self.headers.get('api-key'))}", flush=True)
            self._send({"data": {"activity_id": "act-stub-1"}})
            return

        if "chat/completions" in self.path:
            self._send(_groq_reply(raw))
            return

        if self.path.startswith("/slack"):
            try:
                text = json.loads(raw).get("text", "")
            except ValueError:
                text = raw.decode(errors="replace")
            print(f"SLACK RECEIVED: {text}", flush=True)
            self._send({"ok": True})
            return

        self._send({"error": f"no stub route for POST {self.path}"}, status=404)


def _groq_reply(raw: bytes) -> dict:
    """An OpenAI-shaped completion whose content is the agent's strict JSON."""
    prompt = raw.decode(errors="replace")
    # The prompt carries the summarized readings; if the collector found nothing, the model
    # is expected to return nulls rather than invent numbers. Mirror that here.
    if '"reading_count": 0' in prompt or '"peak_c": null' in prompt:
        decision = {
            "risk_level": "MEDIUM",
            "peak_temperature": None,
            "average_temperature": None,
            "decision": "MODIFY",
            "recommendation": (
                "No temperature readings were returned for this area. Treat the shift as "
                "elevated risk: schedule water breaks every 30 minutes and re-check before start."
            ),
            "reason": (
                "The heatmap carried no readable temperature values, so no peak could be "
                "computed. MEDIUM is applied as a fail-safe floor rather than a measurement."
            ),
        }
    else:
        decision = {
            "risk_level": "HIGH",
            "peak_temperature": 41.2,
            "average_temperature": 38.9,
            "decision": "RESCHEDULE",
            "recommendation": (
                "Move the pour to before 09:00 or after 18:00. If work must proceed, rotate "
                "crews every 20 minutes with shaded rest and one litre of water per hour."
            ),
            "reason": (
                "Peak temperature of 41.2°C is at or above the 33°C HIGH threshold, which "
                "maps to RESCHEDULE. The 38.9°C average means the exposure is sustained "
                "rather than a brief spike."
            ),
        }
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": 0,
        "model": "openai/gpt-oss-120b",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": json.dumps(decision)},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def main() -> None:
    global MODE
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8210)
    parser.add_argument("--mode", default="complete", choices=["complete", "never", "no-readings"])
    args = parser.parse_args()
    MODE = args.mode

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"stub upstream on http://127.0.0.1:{args.port} (mode={MODE})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
