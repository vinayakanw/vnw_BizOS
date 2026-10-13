import asyncio
import logging
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import analytics, approvals, auth, chat_admin, demo, documents, faqs, founder, home, integrations, knowledge, leads, orders, products, profile, public, public_quote, quotes, sales, support, workflows
from app.automation import scheduler
from app.core.config import production_problems, settings
from app.core.db import engine
from app.models import Base

log = logging.getLogger("bizos")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def _check_migrations() -> None:
    """Postgres schema is managed by Alembic. Refuse to run against a database that is behind."""
    from alembic.config import Config
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
    if current != head:
        raise RuntimeError(
            f"Database schema is at '{current}' but the code expects '{head}'. Run:  alembic upgrade head   "
            "(an existing database created before migrations needs:  alembic stamp 0001  first)"
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment == "production":
        problems = production_problems(settings)
        if problems:
            raise RuntimeError("Unsafe production configuration:\n- " + "\n- ".join(problems))
    if engine.dialect.name == "postgresql":
        _check_migrations()
    else:
        Base.metadata.create_all(engine)  # SQLite is for tests only
    task = None
    if settings.scheduler_interval_seconds > 0 and settings.run_scheduler_in_api:
        task = asyncio.create_task(scheduler.loop())
    try:
        yield
    finally:
        if task:
            task.cancel()


app = FastAPI(title="BizOS API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def request_context(request: Request, call_next):
    """Request id, one access-log line per request, and basic security headers."""
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.monotonic()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("Unhandled error rid=%s %s %s", rid, request.method, request.url.path)
        response = JSONResponse({"detail": "Internal server error", "request_id": rid}, status_code=500)
    ms = int((time.monotonic() - started) * 1000)
    if request.url.path != "/health":
        log.info("rid=%s %s %s -> %s %sms", rid, request.method, request.url.path, response.status_code, ms)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path.startswith("/auth"):
        response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(auth.router)
app.include_router(profile.router)
app.include_router(products.router)
app.include_router(faqs.router)
app.include_router(documents.router)
app.include_router(knowledge.router)
app.include_router(sales.router)
app.include_router(analytics.router)
app.include_router(support.router)
app.include_router(founder.router)
app.include_router(integrations.router)
app.include_router(chat_admin.router)
app.include_router(home.router)
app.include_router(public.router)
app.include_router(public_quote.router)
app.include_router(quotes.router)
app.include_router(orders.router)
app.include_router(leads.router)
app.include_router(approvals.router)
app.include_router(workflows.router)
app.include_router(demo.router)


@app.get("/health", tags=["system"])
def health() -> dict:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok", "db": "ok"}
