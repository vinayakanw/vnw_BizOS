import os
import tempfile

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///./test.db")
os.environ.setdefault("JWT_SECRET", "test-secret-that-is-at-least-32-bytes-long")
os.environ.setdefault("UPLOAD_DIR", tempfile.mkdtemp(prefix="bizos-uploads-"))
os.environ.setdefault("EMBEDDING_PROVIDER", "fake")
os.environ.setdefault("KNOWLEDGE_MIN_SCORE", "0.1")
os.environ.setdefault("SCHEDULER_INTERVAL_SECONDS", "0")
os.environ.setdefault("ALLOW_PRIVATE_HOSTS", "true")

import pytest
from fastapi.testclient import TestClient

from app.core.db import engine
from app.main import app
from app.models import Base


@pytest.fixture(autouse=True)
def _reset_llm():
    from app.core import ratelimit
    from app.llm.factory import set_llm

    ratelimit.reset()
    set_llm(None)
    yield
    set_llm(None)


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with TestClient(app) as c:
        yield c


def register(client, org="Acme", email="a@acme.com"):
    r = client.post(
        "/auth/register",
        json={"org_name": org, "full_name": "Alice Owner", "email": email, "password": "password123"},
    )
    assert r.status_code == 201, r.text
    client.cookies.clear()  # tests authenticate with explicit headers
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture()
def two_orgs(client):
    return register(client, "Org A", "a@a.com"), register(client, "Org B", "b@b.com")
