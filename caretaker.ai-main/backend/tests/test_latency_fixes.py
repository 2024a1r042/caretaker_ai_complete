"""
Locks in the latency / API-key fixes:
  • exhausted daily quota fails instantly and stops calling Google
  • a rejected key fails on the first request
  • one total time budget across fallbacks
  • 'thinking' disabled for fast chat calls on 2.5-Flash
  • a slow Gemini call no longer freezes other API requests
  • TTS without credentials returns instantly
  • /api/health/ai explains the situation
"""
import json
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import utils.gemini_client as g


class R:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body or {}
        self.text = json.dumps(self._b)

    def json(self):
        return self._b


DAY = {"error": {"code": 429, "details": [
    {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
     "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "40s"}]}}
OK = {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}


@pytest.fixture()
def gem(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaTEST-KEY-123456")
    monkeypatch.delenv("GEMINI_API_ENDPOINT", raising=False)
    g._cooldown_until.clear(); g._missing_models.clear(); g._cooldown_reason.clear()
    g._key_state.update(fingerprint=None, invalid=False, reason="")
    calls = []

    def install(fn):
        def post(url, json=None, **k):
            calls.append((url.split("/models/")[1].split(":")[0] if "/models/" in url else url, json))
            return fn(len(calls))
        monkeypatch.setattr(g._session, "post", post)
    yield install, calls
    monkeypatch.setenv("GEMINI_API_KEY", "")


def test_daily_quota_fails_fast_then_stops_calling(gem):
    install, calls = gem
    install(lambda i: R(429, DAY))
    t = time.monotonic()
    assert g.call_gemini({"contents": []}, timeout=25) is None
    assert time.monotonic() - t < 0.5 and len(calls) == 3        # was 18 s and 9 requests
    for _ in range(10):
        assert g.call_gemini({"contents": []}) is None
    assert len(calls) == 3                                        # no further requests until reset
    st = g.gemini_status()
    assert set(st["models_cooling_down"]) == set(st["models_in_order"])


def test_rejected_key_fails_on_first_request(gem):
    install, calls = gem
    install(lambda i: R(400, {"error": {"message": "API key not valid. Please pass a valid API key."}}))
    assert g.call_gemini({}) is None and g.call_gemini({}) is None
    assert len(calls) == 1 and g.gemini_status()["key_rejected"]


def test_falls_back_when_primary_exhausted(gem):
    install, calls = gem
    install(lambda i: R(429, DAY) if i == 1 else R(200, OK))
    assert g.call_gemini({}) is not None and calls[1][0] != calls[0][0]


def test_total_time_budget_is_respected(gem, monkeypatch):
    install, calls = gem

    def slow(i):
        time.sleep(1.2)
        return R(503)
    install(slow)
    t = time.monotonic()
    g.call_gemini({}, timeout=3)
    assert time.monotonic() - t < 4.0


def test_fast_mode_turns_off_thinking_on_25_flash(gem, monkeypatch):
    install, calls = gem
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    install(lambda i: R(200, OK))
    g.call_gemini({"generationConfig": {"temperature": 0.7}}, fast=True)
    assert calls[0][1]["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    monkeypatch.delenv("GEMINI_MODEL")


def test_endpoint_override_not_reused_for_fallbacks(gem, monkeypatch):
    install, calls = gem
    monkeypatch.setenv("GEMINI_API_ENDPOINT", "https://example.invalid/custom")
    install(lambda i: R(429, DAY) if i == 1 else R(200, OK))
    g.call_gemini({})
    assert calls[0][0].startswith("https://example.invalid") and "generativelanguage" not in calls[0][0]
    assert calls[1][0] in g.FALLBACK_MODELS


def test_tts_without_credentials_is_instant(monkeypatch):
    import utils.tts_handler as tts
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setattr(tts, "_tts_unavailable", False)
    monkeypatch.setattr(tts, "_client", None)
    t = time.monotonic()
    assert tts.generate_speech_base64("namaste") == "" and tts.generate_speech_base64("again") == ""
    assert time.monotonic() - t < 0.2
    assert tts.tts_status()["available"] is False


def test_slow_gemini_no_longer_freezes_other_requests(monkeypatch, people, token):
    """voice_bot_chat used to be `async def` with a blocking Gemini call → every request waited."""
    import routes.voice_bot as vb
    monkeypatch.setattr(vb, "call_gemini", lambda *a, **k: (time.sleep(2.0), None)[1])
    monkeypatch.setattr(vb, "analyze_sentiment_with_history", lambda *a, **k: {"current_mood": "neutral"})
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    app = FastAPI()
    app.include_router(vb.router, prefix="/api")

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    client = TestClient(app)
    _, rec = people
    th = threading.Thread(target=lambda: client.post("/api/voice-bot/chat", json={"recipient_id": rec.id, "text": "hello"},
                                                       headers={"Authorization": f"Bearer {token}"}))
    th.start()
    time.sleep(0.3)
    t = time.monotonic()
    assert client.get("/api/ping").status_code == 200
    assert time.monotonic() - t < 0.5          # answered while Gemini is still "thinking"
    th.join()
    monkeypatch.setenv("GEMINI_API_KEY", "")


def test_health_endpoint_explains(gem):
    install, _ = gem
    install(lambda i: R(429, DAY))
    g.call_gemini({})
    from routes import health
    app = FastAPI()
    app.include_router(health.router, prefix="/api")
    r = TestClient(app).get("/api/health/ai").json()
    assert r["ok"] is False and r["database"]["ok"] is True
    assert any("out of quota" in a for a in r["advice"])
