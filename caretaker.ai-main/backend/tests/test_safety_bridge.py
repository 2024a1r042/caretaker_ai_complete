"""Camera fall → Saathi speaks to them by name → their answer decides the escalation."""
import asyncio

import pytest

from services import personalization as P
from services.safety_bridge import SafetyBridge
from tables.safety_events import SafetyEvent, SafetyStatusEnum

FALL = {"type": "fall_confirmed", "fall_type": "hard_fall", "severity": "high", "confidence": 0.82,
        "explanation": "Hard fall: Head dropped 70% of standing height in 0.7 s.",
        "evidence": [{"signal": "head_drop", "passed": True, "text": "Head dropped 70%"}]}


class FakeWS:
    def __init__(self): self.sent = []
    async def send_json(self, m): self.sent.append(m)


@pytest.fixture()
def bridge(people, db):
    _, rec = people
    P.update_profile(db, rec.id, {"preferred_name": "Amma",
                                  "family_members": [{"name": "Rahul", "relation": "son", "is_emergency_contact": True}]})
    b = SafetyBridge()
    b.mails, b.emits = [], []

    async def mail(to, subject, html, image): b.mails.append((to, subject, html))

    async def emit(name, payload, **k): b.emits.append((name, payload))
    b.email_sender, b.sio_emit, b.tts = mail, emit, (lambda text, lang: "")
    return b


def status(db, eid):
    db.expire_all()
    return db.query(SafetyEvent).get(eid).status


def test_classify_answers():
    c = SafetyBridge.classify_response
    for s in ["main theek hoon", "I'm fine", "haan ji theek hai", "chot nahi lagi", "ठीक हूँ", "no pain, don't worry"]:
        assert c(s) == "ok", s
    for s in ["madad karo", "help", "bahut dard ho raha hai", "uth nahi pa rahi", "main theek nahi hoon",
              "I can't get up", "not okay", "मदद"]:
        assert c(s) == "help", s
    assert c("hmm") == "unclear"


def test_fall_checkin_then_ok(bridge, people, db):
    ct, rec = people
    ws = FakeWS()
    bridge.register(rec.id, ws)

    async def flow():
        eid = await bridge.handle_engine_event(FALL, rec.id, ct.id, "browser_live")
        res = await bridge.handle_response(eid, "haan main theek hoon, chot nahi lagi")
        return eid, res
    eid, res = asyncio.run(flow())
    checkin = ws.sent[0]
    assert checkin["type"] == "safety_checkin" and checkin["text"].startswith("Amma, kya aap theek hain")
    assert "Rahul" in checkin["text"]
    assert res["verdict"] == "ok" and status(db, eid) == SafetyStatusEnum.resolved_ok
    assert bridge.mails and "says they are OK" in bridge.mails[0][1]
    assert db.query(SafetyEvent).get(eid).evidence[0]["signal"] == "head_drop"


def test_help_escalates_immediately(bridge, people, db):
    ct, rec = people
    bridge.register(rec.id, FakeWS())

    async def flow():
        eid = await bridge.handle_engine_event(FALL, rec.id, ct.id, "browser_live")
        return eid, await bridge.handle_response(eid, "bahut dard hai, madad karo")
    eid, res = asyncio.run(flow())
    assert res["status"] == "escalated" and status(db, eid) == SafetyStatusEnum.escalated
    assert "Rahul" in res["reply"] and any("may need help" in m[1] for m in bridge.mails)


def test_no_answer_escalates_after_window(bridge, people, db, monkeypatch):
    import services.safety_bridge as sb
    monkeypatch.setitem(sb.RESPONSE_WINDOW_S, "high", 0.2)
    ct, rec = people
    ws = FakeWS()
    bridge.register(rec.id, ws)

    async def flow():
        eid = await bridge.handle_engine_event(FALL, rec.id, ct.id, "browser_live")
        await asyncio.sleep(0.5)
        return eid
    eid = asyncio.run(flow())
    assert status(db, eid) == SafetyStatusEnum.escalated
    assert ws.sent[-1]["type"] == "safety_update" and ws.sent[-1]["status"] == "escalated"


def test_no_screen_open_escalates_at_once(bridge, people, db):
    ct, rec = people
    eid = asyncio.run(bridge.handle_engine_event(FALL, rec.id, ct.id, "camera_session"))
    assert status(db, eid) == SafetyStatusEnum.escalated
    assert "not open" in db.query(SafetyEvent).get(eid).escalation_reason


def test_long_lie_is_critical_even_after_ok(bridge, people, db):
    ct, rec = people
    bridge.register(rec.id, FakeWS())

    async def flow():
        eid = await bridge.handle_engine_event(FALL, rec.id, ct.id, "browser_live")
        await bridge.handle_response(eid, "theek hoon")
        await bridge.handle_engine_event({"type": "long_lie", "explanation": "Still on the floor for 30 s",
                                          "time_on_ground_s": 31}, rec.id, ct.id, "browser_live")
        return eid
    asyncio.run(flow())
    db.expire_all()
    row = db.query(SafetyEvent).filter(SafetyEvent.care_recipient_id == rec.id).order_by(SafetyEvent.id.desc()).first()
    assert row.severity == "critical" and row.status == SafetyStatusEnum.escalated


def test_fall_is_remembered_in_next_conversation(bridge, people, db):
    ct, rec = people
    bridge.register(rec.id, FakeWS())

    async def flow():
        eid = await bridge.handle_engine_event(FALL, rec.id, ct.id, "browser_live")
        await bridge.handle_response(eid, "I'm fine")
    asyncio.run(flow())
    block = P.personal_prompt_block(P.build_personal_context(db, rec.id, "", rec.full_name))
    assert "RECENT SAFETY EVENT" in block and "hard fall" in block
