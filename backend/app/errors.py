"""Turning internal failures into something the dashboard can put on screen.

Every error the agent loop can hit is translated here into one `ApiError`, carrying a
sentence written for the person looking at the dashboard rather than for whoever reads the
traceback. The internal message still exists — it goes to the log, at the same moment, under
the same `code` — so a failed demo is diagnosable from the uvicorn console without the
browser having to display any of it.

**The upstream error text is deliberately not returned.** It would be genuinely handy during
development, but `FortyGuardError` embeds up to 300 characters of FortyGuard's response body
and `AgentError` embeds Groq's, and an upstream that echoes a rejected request back would put
an API key in a browser payload (CLAUDE.md → "never expose FORTYGUARD_API_KEY, GROQ_API_KEY
... to the frontend"). `hint` replaces it: written here, per code, so it can say where to look
without quoting anything an upstream sent us.

`retryable` is the one field worth acting on programmatically — it distinguishes "press the
button again and it will probably work" (Groq was busy, FortyGuard was slow) from "pressing
it again will fail the same way" (a key is missing, the AOI is malformed).
"""

from typing import Any

import httpx
from fastapi import Request, status
from fastapi.exceptions import HTTPException, RequestValidationError
from fastapi.responses import JSONResponse

from .agent import AgentError, AgentNotConfigured, AgentRateLimited, AgentTimeout
from .services.fortyguard import (
    FortyGuardError,
    FortyGuardNotConfigured,
    FortyGuardTimeout,
)


class ApiError(HTTPException):
    """An HTTPException that also carries a machine-readable code and a hint.

    Subclasses `HTTPException` so `detail` keeps working for any client that only reads
    FastAPI's default shape; `handle_api_error` adds the rest.
    """

    def __init__(
        self,
        status_code: int,
        *,
        code: str,
        message: str,
        hint: str,
        retryable: bool,
        cause: str,
        headers: dict[str, str] | None = None,
    ):
        # `detail` is the human sentence, not the internal one: a client that ignores
        # everything below still shows something a supervisor can read.
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.message = message
        self.hint = hint
        self.retryable = retryable
        # Never serialized. Logged by the handler so the console shows the real reason.
        self.cause = cause

    def body(self) -> dict[str, Any]:
        return {
            "detail": self.message,
            "error": {
                "code": self.code,
                "message": self.message,
                "hint": self.hint,
                "retryable": self.retryable,
            },
        }


def _seconds(value: float | None) -> str:
    """A retry delay phrased for a human, or a vague fallback when Groq did not say."""
    if value is None:
        return "in a few seconds"
    if value < 60:
        return f"in about {value:.0f} seconds"
    return f"in about {value / 60:.0f} minutes"


def as_api_error(exc: Exception) -> ApiError:
    """Map one internal failure onto its HTTP response.

    Ordered most specific first: `FortyGuardTimeout` is a `FortyGuardError`, and
    `AgentTimeout` / `AgentRateLimited` / `AgentNotConfigured` are all `AgentError`.
    """
    # --- FortyGuard ---------------------------------------------------------------
    if isinstance(exc, FortyGuardNotConfigured):
        return ApiError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="fortyguard_not_configured",
            message="This server has no FortyGuard API key, so it cannot read temperatures.",
            hint="Set FORTYGUARD_API_KEY in backend/.env and restart uvicorn.",
            retryable=False,
            cause=str(exc),
        )
    if isinstance(exc, FortyGuardTimeout):
        return ApiError(
            status.HTTP_504_GATEWAY_TIMEOUT,
            code="fortyguard_timeout",
            message=(
                "The temperature service did not finish in time. Nothing is wrong with "
                "the request — try again."
            ),
            hint=(
                "FortyGuard heatmap jobs are asynchronous. Raise POLL_MAX_ATTEMPTS in "
                "backend/.env if large areas routinely need longer."
            ),
            retryable=True,
            cause=str(exc),
        )
    if isinstance(exc, FortyGuardError):
        return ApiError(
            status.HTTP_502_BAD_GATEWAY,
            code="fortyguard_failed",
            message=(
                "The temperature service rejected this request, so there is no heat data "
                "to assess."
            ),
            hint=(
                "Check FORTYGUARD_API_KEY and the area coordinates. The backend log has "
                "FortyGuard's own response."
            ),
            retryable=False,
            cause=str(exc),
        )

    # --- The network underneath FortyGuard ----------------------------------------
    # `httpx` raises these out of the client rather than through `FortyGuardError`, and a
    # read timeout is a timeout: it belongs on 504 with its siblings, not on 502.
    if isinstance(exc, httpx.TimeoutException):
        return ApiError(
            status.HTTP_504_GATEWAY_TIMEOUT,
            code="fortyguard_timeout",
            message=(
                "The temperature service did not respond in time. Try again."
            ),
            hint=(
                "This was a network timeout rather than a slow job. Raise "
                "HTTP_TIMEOUT_SECONDS in backend/.env if it persists."
            ),
            retryable=True,
            cause=str(exc),
        )
    if isinstance(exc, httpx.HTTPError):
        return ApiError(
            status.HTTP_502_BAD_GATEWAY,
            code="fortyguard_unreachable",
            message="Could not reach the temperature service. Check the connection and retry.",
            hint="Confirm FORTYGUARD_BASE_URL and that this machine has internet access.",
            retryable=True,
            cause=str(exc),
        )
    if isinstance(exc, httpx.InvalidURL):
        # Not an `httpx.HTTPError` — it inherits straight from `Exception`, so it has to be
        # named separately or it escapes as an unhandled 500.
        return ApiError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="fortyguard_not_configured",
            message="This server's FortyGuard address is malformed, so no request could be sent.",
            hint="Fix FORTYGUARD_BASE_URL in backend/.env — it must be a full https:// URL.",
            retryable=False,
            cause=str(exc),
        )

    # --- The reasoning step -------------------------------------------------------
    if isinstance(exc, AgentNotConfigured):
        return ApiError(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="agent_not_configured",
            message="This server has no Groq API key, so it cannot assess the heat data.",
            hint="Set GROQ_API_KEY in backend/.env and restart uvicorn.",
            retryable=False,
            cause=str(exc),
        )
    if isinstance(exc, AgentRateLimited):
        return ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            code="agent_rate_limited",
            message=(
                "The reasoning service is rate-limited. Try again "
                f"{_seconds(exc.retry_after_seconds)}."
            ),
            hint=(
                "Groq's free tier limits requests per minute. openai/gpt-oss-120b has more "
                "headroom if this happens during a demo."
            ),
            retryable=True,
            # Standards-correct, and lets the dashboard time its own retry.
            headers=(
                {"Retry-After": str(int(exc.retry_after_seconds))}
                if exc.retry_after_seconds is not None
                else None
            ),
            cause=str(exc),
        )
    if isinstance(exc, AgentTimeout):
        return ApiError(
            status.HTTP_504_GATEWAY_TIMEOUT,
            code="agent_timeout",
            message=(
                "The heat data was read successfully, but the assessment took too long to "
                "come back. Try again in a moment."
            ),
            hint=(
                "AGENT_DEADLINE_SECONDS in backend/.env caps this. Groq's first call of a "
                "session is often the slowest."
            ),
            retryable=True,
            cause=str(exc),
        )
    if isinstance(exc, AgentError):
        return ApiError(
            status.HTTP_502_BAD_GATEWAY,
            code="agent_failed",
            message=(
                "The heat data was read successfully, but the assessment came back unusable, "
                "so no decision was issued. Try again."
            ),
            # Retryable, unlike the FortyGuard equivalent: this is usually a model that
            # replied off-schema twice, and sampling makes the next attempt a real coin flip.
            hint=(
                "Verify the model id with `uv run python scripts/check_groq.py`. The backend "
                "log has the reply that was rejected."
            ),
            retryable=True,
            cause=str(exc),
        )

    raise exc  # Not ours to translate — let the server's 500 handler own it.


# `RequestValidationError` never reaches `as_api_error`: FastAPI raises it before the route
# body runs, so it is registered as its own handler below.
_INVALID_REQUEST = {
    "code": "invalid_request",
    "hint": (
        "polygon_aoi must be at least 3 [longitude, latitude] pairs in WGS84 degrees, and "
        "date_time must be ISO 8601."
    ),
    "retryable": False,
}


def _describe_validation(exc: RequestValidationError) -> str:
    """One sentence naming the fields that were wrong.

    FastAPI's default 422 body is a list of objects, so a frontend that renders `detail`
    as text gets `[object Object]`. Flattening it here means every status this API can
    return has the same body shape.
    """
    parts = []
    for error in exc.errors()[:4]:
        # Drop the leading "body" segment — it is noise to whoever is reading this.
        location = ".".join(str(p) for p in error["loc"] if p != "body") or "request"
        parts.append(f"{location} ({error['msg']})")
    return "This request could not be read: " + "; ".join(parts) + "." if parts else (
        "This request could not be read."
    )


def register_error_handlers(app: Any, logger: Any) -> None:
    """Wire both handlers onto the app, so every error shares one body shape."""

    @app.exception_handler(ApiError)
    async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        # The one place the internal cause is recorded. Same code the client saw, so a
        # screenshot of the dashboard is enough to find the matching log line.
        logger.error("%s -> HTTP %s: %s", exc.code, exc.status_code, exc.cause)
        return JSONResponse(exc.body(), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        message = _describe_validation(exc)
        logger.info("invalid_request -> HTTP 422: %s", exc.errors()[:4])
        return JSONResponse(
            {"detail": message, "error": {**_INVALID_REQUEST, "message": message}},
            # Literal 422 rather than a Starlette constant: `HTTP_422_UNPROCESSABLE_ENTITY`
            # is deprecated in favour of `..._CONTENT`, and the number is not going to move.
            status_code=422,
        )
