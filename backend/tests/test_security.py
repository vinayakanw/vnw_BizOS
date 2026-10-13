from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.core import ratelimit
from app.core.config import Settings, production_problems, settings
from app.core.db import SessionLocal
from app.models import RefreshToken

ORIGIN = {"Origin": "http://localhost:5173"}
BODY = {"org_name": "Acme", "full_name": "Al", "email": "al@acme.com", "password": "password123"}


def _login(client):
    r = client.post("/auth/register", json=BODY)
    assert r.status_code == 201
    return r


def test_cookies_are_httponly_and_scoped(client):
    r = _login(client)
    cookies = r.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith("bizos_access="))
    refresh = next(c for c in cookies if c.startswith("bizos_refresh="))
    for c in (access, refresh):
        assert "HttpOnly" in c and "SameSite=lax" in c
    assert "Path=/;" in access + ";" and "Path=/auth" in refresh
    assert client.get("/auth/me").status_code == 200  # cookie alone authenticates


def test_cookie_auth_requires_allowed_origin_on_writes(client):
    _login(client)
    faq = {"question": "Q?", "answer": "A."}
    assert client.post("/faqs", json=faq).status_code == 403
    assert client.post("/faqs", json=faq, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/faqs", json=faq, headers=ORIGIN).status_code in (200, 201)
    assert client.get("/faqs").status_code == 200  # reads need no origin


def test_bearer_header_still_works_without_origin(client):
    token = _login(client).json()["access_token"]
    client.cookies.clear()
    r = client.post("/faqs", json={"question": "Q?", "answer": "A."}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code in (200, 201)


def test_refresh_rotates_and_old_token_is_rejected(client):
    _login(client)
    old = client.cookies.get("bizos_refresh", path="/auth")
    assert client.post("/auth/refresh").status_code == 200
    new = client.cookies.get("bizos_refresh", path="/auth")
    assert new and new != old
    # replaying the old token fails and kills the whole family, including the new token
    client.cookies.clear()
    client.cookies.set("bizos_refresh", old, path="/auth")
    assert client.post("/auth/refresh").status_code == 401
    client.cookies.clear()
    client.cookies.set("bizos_refresh", new, path="/auth")
    assert client.post("/auth/refresh").status_code == 401


def test_refresh_restores_access_after_it_expires(client):
    _login(client)
    client.cookies.delete("bizos_access", path="/")  # as if the 15 minute cookie aged out
    assert client.get("/auth/me").status_code == 401
    assert client.post("/auth/refresh").status_code == 200
    assert client.get("/auth/me").status_code == 200


def test_expired_refresh_token_is_rejected(client):
    _login(client)
    with SessionLocal() as db:
        for t in db.query(RefreshToken).all():
            t.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.post("/auth/refresh").status_code == 401


def test_logout_revokes_the_session(client):
    _login(client)
    raw = client.cookies.get("bizos_refresh", path="/auth")
    assert client.post("/auth/logout").status_code == 200
    client.cookies.clear()
    client.cookies.set("bizos_refresh", raw, path="/auth")
    assert client.post("/auth/refresh").status_code == 401
    with SessionLocal() as db:
        assert all(t.revoked_at for t in db.query(RefreshToken).all())


def test_refresh_tokens_are_stored_hashed(client):
    _login(client)
    raw = client.cookies.get("bizos_refresh", path="/auth")
    with SessionLocal() as db:
        assert raw not in {t.token_hash for t in db.query(RefreshToken).all()}


def test_login_is_rate_limited_per_account(client):
    _login(client)
    codes = [client.post("/auth/login", json={"email": "al@acme.com", "password": "wrong-password"}).status_code for _ in range(10)]
    assert codes[:8] == [401] * 8 and codes[8] == 429
    r = client.post("/auth/login", json={"email": "al@acme.com", "password": "password123"})
    assert r.status_code == 429 and "Retry-After" in r.headers  # even the right password is blocked for a while


def test_llm_endpoints_are_rate_limited_per_org(client, two_orgs, monkeypatch):
    a, b = two_orgs
    from app.llm.factory import set_llm
    from tests.test_founder import FounderLLM

    set_llm(FounderLLM({"headline": "h", "summary": "s", "priorities": []}))
    for _ in range(30):
        assert client.post("/agents/founder/briefing", headers=a, json={}).status_code == 200
    assert client.post("/agents/founder/briefing", headers=a, json={}).status_code == 429
    assert client.post("/agents/founder/briefing", headers=b, json={}).status_code == 200  # other tenant unaffected


def test_rate_limit_window_expires():
    ratelimit.reset()
    assert ratelimit.hit("k", 2, 60) is None and ratelimit.hit("k", 2, 60) is None
    assert ratelimit.hit("k", 2, 60) >= 1
    ratelimit.reset()
    assert ratelimit.hit("k", 2, 60) is None


def test_production_config_checks():
    good = Settings(jwt_secret="x" * 40, cookie_secure=True, cors_origins="https://app.example.com", public_app_url="https://app.example.com", allow_private_hosts=False, environment="production")
    assert production_problems(good) == []
    bad = Settings(jwt_secret="dev-only-secret-change-me", cookie_secure=False, cors_origins="http://localhost:5173", allow_private_hosts=True)
    assert len(production_problems(bad)) == 5


def test_security_headers_and_request_id(client):
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123" and r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"


def test_migrations_match_the_models(tmp_path, monkeypatch):
    """alembic upgrade head on an empty database must produce exactly the schema the models describe."""
    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parent.parent
    monkeypatch.setattr(settings, "database_url", f"sqlite+pysqlite:///{tmp_path / 'm.db'}")
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "alembic"))
    command.upgrade(cfg, "head")
    command.check(cfg)  # raises if a model changed without a migration
