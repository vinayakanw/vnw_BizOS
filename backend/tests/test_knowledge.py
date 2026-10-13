import io

from app.knowledge.chunking import chunk_text


def _upload(client, headers, name, data: bytes, ctype="text/plain"):
    r = client.post("/documents", headers=headers, files={"file": (name, data, ctype)})
    assert r.status_code == 201, r.text
    return r.json()


def _search(client, headers, q, k=3):
    r = client.post("/knowledge/search", headers=headers, json={"query": q, "top_k": k})
    assert r.status_code == 200, r.text
    return r.json()


# ---- chunking ----------------------------------------------------------------

def test_chunking_packs_short_paragraphs_and_splits_long_ones():
    text = "\n\n".join(f"Paragraph number {i} about product details." for i in range(10))
    chunks = chunk_text(text, size=120, overlap=20)
    assert len(chunks) > 1 and all(len(c) <= 120 for c in chunks)

    long = "word " * 500
    pieces = chunk_text(long, size=200, overlap=30)
    assert len(pieces) > 5 and all(len(p) <= 200 for p in pieces)
    assert chunk_text("   \n\n  ") == []


# ---- ingestion + search --------------------------------------------------------

def test_upload_is_ingested_and_searchable(client, two_orgs):
    a, _ = two_orgs
    doc = _upload(
        client,
        a,
        "pricing.txt",
        b"Enterprise plan costs 999 dollars per month for 50 seats.\n\n"
        b"Our return policy allows refunds within 30 days of purchase.\n\n"
        b"Shipping across India takes 3 to 5 business days.",
    )
    row = client.get("/documents", headers=a).json()[0]
    assert row["id"] == doc["id"] and row["status"] == "ready" and row["chunk_count"] >= 1

    hits = _search(client, a, "how much is the enterprise plan per month")
    assert hits and "Enterprise plan" in hits[0]["content"]
    assert hits[0]["source_type"] == "document" and hits[0]["title"] == "pricing.txt"
    assert hits[0]["score"] > 0


def test_search_is_tenant_isolated(client, two_orgs):
    a, b = two_orgs
    _upload(client, a, "secret.txt", b"Org A confidential price list: widget costs 12 rupees.")
    assert _search(client, b, "widget price") == []
    assert len(_search(client, a, "widget price")) == 1


def test_faq_is_indexed_updated_and_removed(client, two_orgs):
    a, _ = two_orgs
    faq = client.post(
        "/faqs", headers=a, json={"question": "What is the warranty period?", "answer": "One year on all laptops."}
    ).json()
    hits = _search(client, a, "warranty period")
    assert hits[0]["source_type"] == "faq" and "One year" in hits[0]["content"]

    client.put(
        f"/faqs/{faq['id']}", headers=a, json={"question": "What is the warranty period?", "answer": "Two years."}
    )
    hits = _search(client, a, "warranty period")
    assert len(hits) == 1 and "Two years" in hits[0]["content"]

    client.delete(f"/faqs/{faq['id']}", headers=a)
    assert _search(client, a, "warranty period") == []


def test_deleting_document_removes_its_chunks(client, two_orgs):
    a, _ = two_orgs
    doc = _upload(client, a, "policy.md", b"# Refund policy\n\nRefunds are processed in 7 days.")
    assert _search(client, a, "refund")
    client.delete(f"/documents/{doc['id']}", headers=a)
    assert _search(client, a, "refund") == []


def test_unparseable_document_marked_failed_and_can_be_retried(client, two_orgs):
    a, _ = two_orgs
    doc = _upload(client, a, "broken.pdf", b"this is not really a pdf", "application/pdf")
    row = client.get("/documents", headers=a).json()[0]
    assert row["id"] == doc["id"] and row["status"] == "failed" and row["chunk_count"] == 0
    r = client.post(f"/documents/{doc['id']}/reprocess", headers=a)
    assert r.status_code == 200
    assert client.get("/documents", headers=a).json()[0]["status"] == "failed"


def test_docx_parsing(client, two_orgs):
    from docx import Document as Docx

    buf = io.BytesIO()
    d = Docx()
    d.add_paragraph("Our flagship laptop has a 16GB memory and 1TB SSD.")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text = "Battery"
    t.rows[0].cells[1].text = "12 hours"
    d.save(buf)
    a, _ = two_orgs
    _upload(
        client, a, "specs.docx", buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    hits = _search(client, a, "battery hours")
    assert hits and "12 hours" in hits[0]["content"]


def test_reindex_rebuilds_everything(client, two_orgs):
    from sqlalchemy import delete

    from app.core.db import SessionLocal
    from app.models import Chunk

    a, _ = two_orgs
    _upload(client, a, "a.txt", b"Delivery is free above 5000 rupees.")
    client.post("/faqs", headers=a, json={"question": "Do you ship abroad?", "answer": "Yes, to 20 countries."})
    with SessionLocal() as s:
        s.execute(delete(Chunk))
        s.commit()
    assert _search(client, a, "delivery") == []

    r = client.post("/knowledge/reindex", headers=a)
    assert r.json() == {"documents": 1, "faqs": 1}
    assert _search(client, a, "delivery free") and _search(client, a, "ship abroad")


def test_knowledge_requires_auth(client):
    assert client.post("/knowledge/search", json={"query": "x"}).status_code == 401
    assert client.post("/knowledge/reindex").status_code == 401
