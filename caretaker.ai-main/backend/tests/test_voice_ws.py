"""
The real /ws/voice-chat route, end-to-end (LLM + TTS stubbed):
  hello → this screen is registered for the recipient
  camera fall → Saathi speaks the check-in on THIS socket → answer over the socket → resolved
  proactive → personal opener; chat → memory learned, name used
"""
import json
import sys
import time
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# google-cloud-tts isn't needed for the test — stub it before import
_g = types.ModuleType("google"); _gc = types.ModuleType("google.cloud"); _tts = types.ModuleType("google.cloud.texttospeech")
_gc.texttospeech = _tts; _g.cloud = _gc
sys.modules.setdefault("google", _g); sys.modules.setdefault("google.cloud", _gc); sys.modules.setdefault("google.cloud.texttospeech", _tts)


@pytest.fixture()
def app(monkeypatch):
    import routes.voice_bot_ws as ws
    from services import personalization as P
    from services.safety_bridge import safety_bridge
    prompts, calls = [], []

    def fake_gemini(payload, timeout=0, caller="", *a, **k):
        prompts.append(payload["contents"][0]["parts"][0]["text"])
        calls.append(k.get("fast", a[2] if len(a) > 2 else None))
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(
            {"reply": "Amma, aaj aloo paratha khaya?", "intent": "chat", "search_query": "",
             "mood": "happy", "urgency": "low",
             "remember": [{"category": "preference", "content": "Loves Kishore Kumar songs", "importance": 3}]})}]}}]}
    monkeypatch.setattr(ws, "call_gemini", fake_gemini)
    monkeypatch.setattr(ws, "generate_speech_base64", lambda text, lang: "")
    monkeypatch.setattr(ws, "analyze_sentiment_with_history", lambda *a, **k: {"current_mood": "neutral", "trend": "stable"})

    async def nomail(*a): pass

    async def noemit(*a, **k): pass
    safety_bridge.email_sender, safety_bridge.sio_emit, safety_bridge.tts = nomail, noemit, (lambda t, l: "")
    a = FastAPI()
    a.include_router(ws.router, prefix="/api")
    a.prompts = prompts
    a.calls = calls
    return a


def test_ws_fall_checkin_and_personal_chat(app, people, token, db):
    from services import personalization as P
    from services.safety_bridge import safety_bridge
    ct, rec = people
    P.update_profile(db, rec.id, {"preferred_name": "Amma", "favorite_foods": ["aloo paratha"],
                                  "family_members": [{"name": "Rahul", "relation": "son"}]})
    client = TestClient(app)
    with client.websocket_connect("/api/ws/voice-chat") as ws:
        ws.send_text(json.dumps({"type": "hello", "token": token, "recipient_id": rec.id}))
        assert ws.receive_json()["type"] == "hello_ack"
        assert safety_bridge.listeners(rec.id)

        # camera thread reports a fall → Saathi speaks on this socket
        safety_bridge.report_event({"type": "fall_confirmed", "fall_type": "hard_fall", "severity": "high",
                                    "explanation": "Hard fall: head dropped 90%", "evidence": []},
                                   rec.id, ct.id, source="camera_session")
        msg = ws.receive_json()
        assert msg["type"] == "safety_checkin" and msg["text"].startswith("Amma")

        ws.send_text(json.dumps({"type": "safety_response", "token": token, "recipient_id": rec.id,
                                 "event_id": msg["event_id"], "text": "main theek hoon"}))
        upd = ws.receive_json()
        assert upd["type"] == "safety_update" and upd["verdict"] == "ok"

        # proactive opener: the fall is too fresh for the post-fall follow-up (2 h), so a greeting
        ws.send_text(json.dumps({"type": "proactive", "force": True, "token": token, "recipient_id": rec.id}))
        pro = ws.receive_json()
        assert pro["type"] == "bot_response" and pro["proactive"] is True
        assert "YOU ARE STARTING THE CONVERSATION" in app.prompts[-1]

        # regular chat — personal prompt + memory learned
        ws.send_text(json.dumps({"type": "chat", "token": token, "recipient_id": rec.id,
                                 "text": "Mujhe Kishore Kumar ke gaane bahut pasand hai"}))
        bot = ws.receive_json()
        assert bot["type"] == "bot_response"
        p = app.prompts[-1]
        assert '"Amma"' in p and "User ji" not in p and "RECENT SAFETY EVENT" in p
    from tables.personalization import RecipientMemory
    from tables.conversation_history import ConversationMessage, SenderEnum
    db.expire_all()
    # memory + mood came back INSIDE the single reply call
    assert any(m.content == "Loves Kishore Kumar songs" for m in db.query(RecipientMemory).filter_by(care_recipient_id=rec.id))
    last_user = db.query(ConversationMessage).filter_by(care_recipient_id=rec.id, sender=SenderEnum.user) \
        .order_by(ConversationMessage.id.desc()).first()
    assert last_user.mood_detected.value == "happy"
    assert len(app.prompts) == 2          # proactive + chat — exactly ONE Gemini call per chat message
    assert not safety_bridge.listeners(rec.id)        # unregistered on disconnect


def test_ws_rejects_other_familys_recipient(app, people, token, db):
    from tables.users import CareTaker, CareRecipient
    other = CareTaker(email="x@y.z", username="other_family", phone_number="7000000001", password="x")
    db.add(other); db.commit()
    stranger = CareRecipient(caretaker_id=other.id, full_name="Someone Else", email="se@y.z", phone_number="7000000002")
    db.add(stranger); db.commit()
    with TestClient(app).websocket_connect("/api/ws/voice-chat") as ws:
        ws.send_text(json.dumps({"type": "hello", "token": token, "recipient_id": stranger.id}))
        assert "error" in ws.receive_json()
