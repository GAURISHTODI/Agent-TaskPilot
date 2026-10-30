import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db
from app.llm.factory import build_llm
from app.main import app


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    app.state.llm = build_llm("fake")
    yield TestClient(app)  # no lifespan: tables/seed come from the in-memory fixture
    app.dependency_overrides.clear()


def meta_payload(wa_id, text, mid):
    return {"entry": [{"changes": [{"value": {"contacts": [{"wa_id": wa_id, "profile": {"name": "Test"}}],
                                              "messages": [{"from": wa_id, "id": mid, "type": "text", "text": {"body": text}}]}}]}]}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_sim_to_approval_over_http(client):
    r = client.post("/sim/message", json={"phone": "+91 90000 00001", "text": "Need an AC technician Saturday morning, Koramangala, under 1500"}).json()
    tid = r["task_id"]
    assert client.get("/tasks", params={"status": "AWAITING_APPROVAL"}).json()[0]["id"] == tid
    d = client.get(f"/tasks/{tid}").json()
    assert d["shortlist"] and d["outreach"] and d["audit"]
    oid = d["outreach"][0]["id"]
    ok = client.post(f"/tasks/{tid}/approve", json={"item_type": "vendor_outreach", "item_id": oid, "decision": "approved"})
    assert ok.json()["status"] == "AWAITING_VENDOR"
    again = client.post(f"/tasks/{tid}/approve", json={"item_type": "vendor_outreach", "item_id": oid, "decision": "approved"})
    assert again.status_code == 409
    assert client.post(f"/tasks/{tid}/vendor-reply", json={"outreach_id": oid, "reply": "available, Rs 1200"}).json()["status"] == "CUSTOMER_UPDATE_DRAFTED"
    assert client.get("/metrics/unit-economics").json()["tasks"] == 1


def test_webhook_idempotent(client):
    p = meta_payload("919000000002", "plumber tomorrow in HSR", "wamid.A")
    a = client.post("/webhook/whatsapp", json=p).json()
    b = client.post("/webhook/whatsapp", json=p).json()
    assert a["processed"] == 1 and b["results"][0]["duplicate"] is True
    assert len(client.get("/tasks").json()) == 1


def test_webhook_verify(client):
    ok = client.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "taskpilot-dev", "hub.challenge": "42"})
    assert ok.text == "42"
    assert client.get("/webhook/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "1"}).status_code == 403


def test_404_and_console(client):
    assert client.get("/tasks/999").status_code == 404
    assert "TaskPilot" in client.get("/").text
