LAPTOP = {
    "name": "DevBook 14",
    "sku": "DB14",
    "category": "Laptops",
    "description": "14 inch developer laptop, 16GB RAM",
    "price": 58999,
    "currency": "inr",
    "stock": 40,
    "specs": {"ram": "16GB", "cpu": "Ryzen 7"},
}


def test_profile_roundtrip(client, two_orgs):
    a, b = two_orgs
    assert client.get("/profile", headers=a).json()["name"] == "Org A"
    r = client.put(
        "/profile",
        headers=a,
        json={"industry": "Hardware", "website": "https://a.com", "tone": "friendly", "discount_policy": "Max 5%"},
    )
    assert r.status_code == 200
    got = client.get("/profile", headers=a).json()
    assert got["industry"] == "Hardware" and got["discount_policy"] == "Max 5%"
    # org B untouched
    assert client.get("/profile", headers=b).json()["industry"] is None


def test_product_crud_and_search(client, two_orgs):
    a, _ = two_orgs
    created = client.post("/products", headers=a, json=LAPTOP)
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert created.json()["currency"] == "INR"

    client.post("/products", headers=a, json={**LAPTOP, "name": "Office Mouse", "category": "Accessories", "price": 499})
    assert len(client.get("/products", headers=a).json()) == 2
    found = client.get("/products", headers=a, params={"q": "devbook"}).json()
    assert [p["name"] for p in found] == ["DevBook 14"]

    upd = client.put(f"/products/{pid}", headers=a, json={**LAPTOP, "price": 55999})
    assert upd.json()["price"] == 55999

    assert client.delete(f"/products/{pid}", headers=a).status_code == 204
    assert client.put(f"/products/{pid}", headers=a, json=LAPTOP).status_code == 404


def test_product_validation(client, two_orgs):
    a, _ = two_orgs
    assert client.post("/products", headers=a, json={**LAPTOP, "price": -1}).status_code == 422
    assert client.post("/products", headers=a, json={**LAPTOP, "name": ""}).status_code == 422


def test_products_isolated_between_orgs(client, two_orgs):
    a, b = two_orgs
    pid = client.post("/products", headers=a, json=LAPTOP).json()["id"]
    assert client.get("/products", headers=b).json() == []
    assert client.put(f"/products/{pid}", headers=b, json=LAPTOP).status_code == 404
    assert client.delete(f"/products/{pid}", headers=b).status_code == 404
    assert len(client.get("/products", headers=a).json()) == 1


def test_faq_crud_and_isolation(client, two_orgs):
    a, b = two_orgs
    r = client.post("/faqs", headers=a, json={"question": "Warranty?", "answer": "1 year."})
    assert r.status_code == 201
    fid = r.json()["id"]
    assert client.get("/faqs", headers=b).json() == []
    assert client.delete(f"/faqs/{fid}", headers=b).status_code == 404
    upd = client.put(f"/faqs/{fid}", headers=a, json={"question": "Warranty?", "answer": "2 years."})
    assert upd.json()["answer"] == "2 years."
    assert client.delete(f"/faqs/{fid}", headers=a).status_code == 204


def test_document_upload_list_delete(client, two_orgs):
    a, b = two_orgs
    r = client.post("/documents", headers=a, files={"file": ("pricing.txt", b"Enterprise: 999/mo", "text/plain")})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["filename"] == "pricing.txt" and doc["size_bytes"] == 18 and doc["status"] == "uploaded"
    assert len(client.get("/documents", headers=a).json()) == 1
    assert client.get("/documents", headers=b).json() == []
    assert client.delete(f"/documents/{doc['id']}", headers=b).status_code == 404
    assert client.delete(f"/documents/{doc['id']}", headers=a).status_code == 204
    assert client.get("/documents", headers=a).json() == []


def test_document_rejects_bad_type_empty_and_path_tricks(client, two_orgs):
    a, _ = two_orgs
    assert client.post("/documents", headers=a, files={"file": ("x.exe", b"abc", "application/octet-stream")}).status_code == 415
    assert client.post("/documents", headers=a, files={"file": ("empty.txt", b"", "text/plain")}).status_code == 400
    r = client.post("/documents", headers=a, files={"file": ("../../evil.txt", b"hi", "text/plain")})
    assert r.status_code == 201
    assert r.json()["filename"] == "evil.txt"


def test_endpoints_require_auth(client):
    for path in ("/profile", "/products", "/faqs", "/documents"):
        assert client.get(path).status_code == 401
