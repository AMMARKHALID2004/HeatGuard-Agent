"""FastAPI application entrypoint.

    uvicorn app.main:app --reload --port 8000   (run from backend/)
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .config import get_settings
from .errors import register_error_handlers
from .routers import evaluate
from .schemas import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title="HeatGuard Agent",
    version=__version__,
    description=(
        "Heat-risk agent for outdoor work: reads FortyGuard hyperlocal temperature data, "
        "reasons over fixed risk thresholds, and returns PROCEED / MODIFY / RESCHEDULE."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

app.include_router(evaluate.router)

# Every non-2xx body, 422 included, comes out of here with the same shape.
register_error_handlers(app, logger)


@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    """Liveness plus a boolean-only view of which credentials are configured.

    Reports presence, never values — secrets stay server-side.
    """
    return HealthResponse(
        version=__version__,
        fortyguard_configured=bool(settings.fortyguard_api_key),
        groq_configured=bool(settings.groq_api_key),
        slack_configured=settings.slack_enabled,
    )
