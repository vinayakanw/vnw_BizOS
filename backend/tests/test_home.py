from app.core.db import SessionLocal
from app.models import Lead, LeadTask
from tests.conftest import register
from tests.test_customer_chat import _enable, _start
from tests.test_founder import _org_id

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_home_queue_and_setup_steps(client, two_orgs):
    a, b = two_orgs
    t = client.get("/home/today", headers=a).json()
    assert t["first_name"] == "Alice" and t["queue"] == [] and t["counts"] == {"inbox": 0, "tickets": 0, "approvals": 0}
    assert [s["done"] for s in t["steps"]] == [False] * 7 and t["steps"][-1]["optional"] is True and t["chat_path"] is None

    slug = _enable(client, a)
    token = _start(client, slug, mode="support")
    client.post(f"/public/chat/{slug}/photo", headers={"X-Visitor-Token": token}, files={"file": ("a.png", PNG, "image/png")})
    with SessionLocal() as db:
        org = _org_id(client, a)
        lead = Lead(org_id=org, name="Rahul", status="HOT", score=90)
        db.add(lead)
        db.flush()
        db.add(LeadTask(org_id=org, lead_id=lead.id, title="Quote Q-0001 accepted by Rahul", created_by="Quote page"))
        db.commit()

    t = client.get("/home/today", headers=a).json()
    kinds = [q["kind"] for q in t["queue"]]
    assert kinds[0] == "chat" and "quote" in kinds and "lead" in kinds and kinds.index("quote") < kinds.index("lead")  # urgent first
    assert t["queue"][0]["to"].startswith("/inbox/") and t["counts"]["inbox"] == 1 and t["counts"]["tickets"] == 1
    done = {s["key"]: s["done"] for s in t["steps"]}
    assert done["chat"] and done["try"] and not done["email"] and t["chat_path"] == f"/chat/{slug}"
    assert client.get("/home/counts", headers=a).json() == {"inbox": 1, "tickets": 1, "approvals": 0}

    # another business sees none of it
    other = client.get("/home/today", headers=b).json()
    assert other["queue"] == [] and other["counts"]["inbox"] == 0
    assert client.get("/home/today").status_code == 401
