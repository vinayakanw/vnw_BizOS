def _register(client, org="Acme", email="a@acme.com"):
    r = client.post(
        "/auth/register",
        json={"org_name": org, "full_name": "Alice Owner", "email": email, "password": "password123"},
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]



def _hdr(token):
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "db": "ok"}


def test_register_then_me(client):
    token = _register(client)
    me = client.get("/auth/me", headers=_hdr(token)).json()
    assert me["email"] == "a@acme.com"
    assert me["org"]["name"] == "Acme"
    assert me["role"] == "owner"


def test_login_ok_and_bad_password(client):
    _register(client)
    ok = client.post("/auth/login", json={"email": "a@acme.com", "password": "password123"})
    assert ok.status_code == 200
    bad = client.post("/auth/login", json={"email": "a@acme.com", "password": "wrongpass1"})
    assert bad.status_code == 401


def test_duplicate_email_rejected(client):
    _register(client)
    r = client.post(
        "/auth/register",
        json={"org_name": "Other", "full_name": "Bob", "email": "A@acme.com", "password": "password123"},
    )
    assert r.status_code == 409


def test_me_requires_token(client):
    assert client.get("/auth/me").status_code == 401
    assert client.get("/auth/me", headers=_hdr("garbage")).status_code == 401


def test_tenants_are_separate_orgs(client):
    t1 = _register(client, "Org A", "a@a.com")
    t2 = _register(client, "Org B", "b@b.com")
    m1 = client.get("/auth/me", headers=_hdr(t1)).json()
    m2 = client.get("/auth/me", headers=_hdr(t2)).json()
    assert m1["org"]["id"] != m2["org"]["id"]


def test_token_with_tampered_org_rejected(client):
    from app.core.security import create_access_token

    t1 = _register(client, "Org A", "a@a.com")
    t2 = _register(client, "Org B", "b@b.com")
    user_a = client.get("/auth/me", headers=_hdr(t1)).json()
    org_b = client.get("/auth/me", headers=_hdr(t2)).json()["org"]["id"]
    forged = create_access_token(user_a["id"], org_b)
    assert client.get("/auth/me", headers=_hdr(forged)).status_code == 401
