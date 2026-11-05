"""HTTP routes: the profile page API, and the (previously missing) live log-event endpoint."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import personalization as pr, safety as sr
from services.safety_bridge import safety_bridge


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(pr.router, prefix="/api")
    app.include_router(sr.router, prefix="/api")
    sent = []

    async def mail(*a): sent.append(a)

    async def emit(*a, **k): pass
    safety_bridge.email_sender, safety_bridge.sio_emit, safety_bridge.tts = mail, emit, (lambda t, l: "")
    c = TestClient(app)
    c.sent = sent
    return c


def test_profile_roundtrip_and_preview(client, people, token):
    _, rec = people
    H = {"Authorization": f"Bearer {token}"}
    r = client.put(f"/api/personalization/{rec.id}/profile", headers=H, json={
        "preferred_name": "Amma", "favorite_foods": ["aloo paratha"],
        "daily_routine": [{"time": "07:00", "activity": "morning puja"}]})
    assert r.status_code == 200 and r.json()["profile"]["preferred_name"] == "Amma"
    r = client.get(f"/api/personalization/{rec.id}/context-preview", headers=H).json()
    assert r["address_as"] == "Amma" and "aloo paratha" in r["prompt_block"] and r["next_proactive"]
    r = client.post(f"/api/personalization/{rec.id}/memories", headers=H, json={"content": "Loves Ramayan on TV"})
    mid = r.json()["memory"]["id"]
    assert any(m["id"] == mid for m in client.get(f"/api/personalization/{rec.id}/memories", headers=H).json()["memories"])
    assert client.delete(f"/api/personalization/{rec.id}/memories/{mid}", headers=H).status_code == 200
    assert not any(m["id"] == mid for m in client.get(f"/api/personalization/{rec.id}/memories", headers=H).json()["memories"])


def test_other_family_cannot_read_profile(client, people):
    from repository.users import JWTRepo
    _, rec = people
    stranger = JWTRepo.generate_token({"sub": "someone-else"})
    r = client.get(f"/api/personalization/{rec.id}/profile", headers={"Authorization": f"Bearer {stranger}"})
    assert r.status_code == 404


def test_live_log_event_stores_evidence(client, people, token):
    _, rec = people
    H = {"Authorization": f"Bearer {token}"}
    ev = {"type": "fall_confirmed", "fall_type": "fall", "severity": "high", "confidence": 0.7,
          "explanation": "Fall: Head dropped 60%", "evidence": [{"signal": "head_drop", "passed": True, "text": "x"}]}
    r = client.post("/api/video-monitoring/log-event", headers=H, json={"type": "fall", "recipient_id": rec.id, "event": ev})
    assert r.status_code == 200 and r.json()["event_id"]
    rows = client.get(f"/api/safety/events/{rec.id}", headers=H).json()["events"]
    assert rows[0]["explanation"] == "Fall: Head dropped 60%" and rows[0]["evidence"][0]["signal"] == "head_drop"
    # no Saathi screen open in this test → family is alerted straight away
    assert rows[0]["status"] == "escalated" and client.sent
