"""Audio: one cough = one event (not 2-3 overlapping windows), reasons are given, coughing fits are noticed."""
import asyncio
import datetime as dt

import numpy as np
import pytest

from services.audio_episodes import CoughEpisodeTracker, FIT_MIN_COUGHS


def win(label, conf, why=("sudden start",)):
    return {"predicted": label, "confidence": conf, "why": list(why)}


def test_overlapping_windows_merge_into_one_cough():
    tr = CoughEpisodeTracker()
    evs = []
    t = 0.0
    for label, conf in [("Noise", 80), ("Cough", 72), ("Cough", 88), ("Cough", 65), ("Noise", 90), ("Noise", 90)]:
        evs += tr.update(t, win(label, conf))
        t += 0.25
    evs += tr.flush(t + 2)
    sounds = [e for e in evs if e["kind"] == "sound"]
    assert len(sounds) == 1 and sounds[0]["type"] == "Cough" and sounds[0]["confidence"] == 88


def test_low_confidence_is_ignored_and_types_split():
    tr = CoughEpisodeTracker()
    evs = tr.update(0, win("Cough", 40)) + tr.update(0.25, win("Sneeze", 75)) + tr.update(0.5, win("Cough", 80))
    evs += tr.flush(5)
    assert [e["type"] for e in evs if e["kind"] == "sound"] == ["Sneeze", "Cough"]


def test_coughing_fit_detected_once():
    tr = CoughEpisodeTracker()
    evs = []
    t = 0.0
    for _ in range(FIT_MIN_COUGHS + 3):
        evs += tr.update(t, win("Cough", 85)); t += 0.25
        evs += tr.update(t, win("Noise", 90)); t += 6.0
    fits = [e for e in evs if e["kind"] == "fit"]
    assert len(fits) == 1 and fits[0]["coughs"] >= FIT_MIN_COUGHS
    assert "coughs within" in fits[0]["why"][0]


def test_acoustic_classifier_explains_itself():
    librosa = pytest.importorskip("librosa")
    import importlib.util, os
    spec = importlib.util.spec_from_file_location(   # skip the package __init__ (it imports TensorFlow)
        "acoustic_analyzer", os.path.join(os.path.dirname(__file__), "..", "utils", "audio_model", "acoustic_analyzer.py"))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    classify_acoustic = mod.classify_acoustic
    sr = 16000
    silence = np.zeros(sr // 2, dtype=np.float32) + 1e-4 * np.random.RandomState(0).randn(sr // 2).astype(np.float32)
    r = classify_acoustic(silence, sr)
    assert r["predicted"] == "Noise" and r["why"] and "features" in r
    burst = np.zeros(sr // 2, dtype=np.float32)
    rng = np.random.RandomState(1)
    burst[2000:4400] = (0.6 * rng.randn(2400) * np.exp(-np.linspace(0, 5, 2400))).astype(np.float32)
    r = classify_acoustic(burst, sr)
    assert r["predicted"] in ("Cough", "Sneeze") and any("sudden" in w for w in r["why"])


def test_coughing_fit_nudge_reaches_saathi_once(people, db):
    from services.safety_bridge import SafetyBridge
    from services import personalization as P
    from tables.personalization import RecipientMemory
    ct, rec = people
    P.update_profile(db, rec.id, {"preferred_name": "Amma"})
    b = SafetyBridge()
    sent = []

    class WS:
        async def send_json(self, m): sent.append(m)

    async def emit(*a, **k): pass
    b.sio_emit, b.tts = emit, (lambda t, l: "")
    b.register(rec.id, WS())
    n1 = asyncio.run(b.care_nudge(rec.id, "coughing_fit", "6 coughs within 40 seconds"))
    n2 = asyncio.run(b.care_nudge(rec.id, "coughing_fit", "again"))
    assert n1 == 1 and n2 == 0                            # rate-limited
    assert sent[0]["type"] == "care_nudge" and sent[0]["text"].startswith("Amma")
    db.expire_all()
    assert any("coughing fit" in m.content for m in db.query(RecipientMemory).filter_by(care_recipient_id=rec.id))


def test_summary_compares_today_with_usual(people, token, db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routes import audio_events
    from tables.audio_events import AudioEvent, AudioEventType
    ct, rec = people
    now = dt.datetime.utcnow()
    for d in range(1, 7):                                  # 2 coughs on each of the previous 6 days
        for _ in range(2):
            db.add(AudioEvent(caretaker_id=ct.id, care_recipient_id=rec.id, event_type=AudioEventType.cough,
                              confidence=80, detected_at=now - dt.timedelta(days=d)))
    for _ in range(6):                                     # 6 today
        db.add(AudioEvent(caretaker_id=ct.id, care_recipient_id=rec.id, event_type=AudioEventType.cough,
                          confidence=80, detected_at=now - dt.timedelta(minutes=5), notes="sudden start, loud"))
    db.commit()
    app = FastAPI(); app.include_router(audio_events.router, prefix="/api")
    r = TestClient(app).get(f"/api/audio-events/summary?care_recipient_id={rec.id}",
                            headers={"Authorization": f"Bearer {token}"}).json()
    assert r["today"]["cough"] == 6 and r["usual_cough_per_day"] == 2.0
    assert "3.0×" in r["comparison"] and len(r["daily"]) == 7 and sum(r["hourly_today"]) == 6
    assert r["recent"][0]["why"] == "sudden start, loud"
