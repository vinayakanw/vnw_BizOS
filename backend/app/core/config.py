from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://bizos:bizos@localhost:5432/bizos"
    jwt_secret: str = "dev-only-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 15  # access token lifetime. The refresh cookie keeps the session going.
    refresh_expire_days: int = 14
    environment: str = "development"  # set to "production" on the server to turn on startup safety checks
    # Auth cookies. For a frontend and API on different sites (e.g. vercel.app + onrender.com) use samesite=none and secure=true.
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    # Behind a proxy (Render, Fly, nginx) the real client IP is in X-Forwarded-For. Only enable when a proxy really sets it.
    trust_forwarded_for: bool = False
    rate_limit_enabled: bool = True
    # Run the scheduler inside the API process. Turn off when running `python -m app.worker` separately.
    run_scheduler_in_api: bool = True
    cors_origins: str = "http://localhost:5173"
    # Where customers open links from emails and chat (quote page, resume chat). The frontend URL.
    public_app_url: str = "http://localhost:5173"

    upload_dir: str = "./uploads"
    max_upload_mb: int = 10

    # Knowledge base. "local" = fastembed on CPU (no API key). "fake" = deterministic, for tests.
    embedding_provider: str = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384
    chunk_size: int = 800
    chunk_overlap: int = 100

    # LLM. Key goes in backend/.env as LLM_API_KEY, never in code.
    llm_provider: str = "gemini"
    llm_api_key: str = ""
    llm_model: str = "gemini-3.5-flash-lite"
    knowledge_min_score: float = 0.45

    # Background checks (inactive leads). Seconds between runs, 0 turns the scheduler off.
    scheduler_interval_seconds: int = 300

    # Discounts at or below this, on at least this many units, need no human approval.
    auto_discount_max_pct: float = 5.0
    auto_discount_min_qty: int = 10

    # Integrations. Key for encrypting stored credentials (SMTP password). Falls back to a key derived from JWT_SECRET.
    secrets_key: str = ""
    # Tenants choose their own SMTP host. Private/loopback addresses are blocked unless this is true (tests, local dev).
    allow_private_hosts: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

DEFAULT_JWT_SECRET = "dev-only-secret-change-me"


def production_problems(s: Settings) -> list[str]:
    """Things that must be fixed before the app is allowed to start in production."""
    bad = []
    if s.jwt_secret == DEFAULT_JWT_SECRET or len(s.jwt_secret) < 32:
        bad.append("JWT_SECRET must be a random string of at least 32 characters")
    if not s.cookie_secure:
        bad.append("COOKIE_SECURE must be true (cookies only over HTTPS)")
    if s.cookie_samesite.lower() not in ("lax", "strict", "none"):
        bad.append("COOKIE_SAMESITE must be lax, strict or none")
    if s.cookie_samesite.lower() == "none" and not s.cookie_secure:
        bad.append("COOKIE_SAMESITE=none requires COOKIE_SECURE=true")
    if s.allow_private_hosts:
        bad.append("ALLOW_PRIVATE_HOSTS must be false")
    if any(o == "*" or o.startswith("http://localhost") for o in s.cors_origin_list):
        bad.append("CORS_ORIGINS must list only your real frontend URL(s), not * or localhost")
    if not s.public_app_url.startswith("https://"):
        bad.append("PUBLIC_APP_URL must be your real frontend URL starting with https://")
    return bad
