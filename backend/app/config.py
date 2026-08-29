"""Runtime configuration, loaded from the environment or backend/.env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Secrets. Server-side only; never serialized into a response. ---
    fortyguard_api_key: str = ""
    groq_api_key: str = ""
    slack_webhook_url: str | None = None

    # --- Upstream endpoints ---
    fortyguard_base_url: str = "https://api.fortyguard.com/v1"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # OpenStreetMap Nominatim, for the "search any US location" box. Keyless; proxied
    # server-side so a descriptive User-Agent can be sent (browsers forbid setting one).
    nominatim_base_url: str = "https://nominatim.openstreetmap.org"
    # Groq retired the Llama family: `llama-3.3-70b-versatile` (what CLAUDE.md originally
    # specified) now 404s with `model_not_found`. This is Groq's largest production chat
    # model, and it supports the `json_object` response format the agent depends on.
    # `openai/gpt-oss-20b` is the smaller sibling if free-tier rate limits bite.
    groq_model: str = "openai/gpt-oss-120b"


    # --- Bounded polling of the FortyGuard async job ---
    poll_max_attempts: int = 15
    poll_initial_delay_seconds: float = 2.0
    poll_backoff_factor: float = 1.5
    poll_max_delay_seconds: float = 15.0
    http_timeout_seconds: float = 30.0

    # --- Bounded reasoning: ceiling on the whole Groq phase, retries and repair turn
    # included. Without it the SDK will honour a free-tier `Retry-After: 120` twice and the
    # dashboard button spins for minutes.
    agent_deadline_seconds: float = 45.0

    # --- "No readings" fallback for near-real-time requests ---
    # FortyGuard confirmed (2026-08) the API itself is queryable 24/7 for any date/time from
    # 2021-01-01 up to now+12h — there is no "certain hours only" restriction on *access*.
    # But the underlying data is satellite-derived, and a request for the literal current
    # minute can still land in a gap between passes before that imagery has been processed,
    # even though the request itself is perfectly valid. Rather than surface that gap as a
    # false "no data" MODIFY floor, retry the *same* AOI a little further back in time — real
    # FortyGuard data, just the most recent instant it actually has a reading for.
    # Set NOW_FALLBACK_MAX_STEPS=0 to disable and go back to failing fast on an empty grid.
    now_fallback_step_minutes: float = 60.0
    now_fallback_max_steps: int = 3

    # --- CORS: comma-separated list of allowed dashboard origins ---
    cors_allow_origins: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def slack_enabled(self) -> bool:
        return bool(self.slack_webhook_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
