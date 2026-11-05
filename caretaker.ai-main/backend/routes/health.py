"""
GET /api/health/ai — one place to see why Saathi is slow or silent.

Open it in the browser while the backend runs. It answers:
  • is a Gemini key configured, and has Google rejected it?
  • which models are skipped right now because their quota is used up (and for how long)?
  • how long did the last successful Gemini call take?
  • is Cloud TTS configured, or is the browser voice being used?
  • is the database reachable?
No secrets are returned (the key is shown only as its first/last 4 characters).
"""
import time

from fastapi import APIRouter
from sqlalchemy import text

router = APIRouter(tags=["Health"])


@router.get("/health/ai")
def ai_health():
    from utils.gemini_client import gemini_status
    from utils.tts_handler import tts_status
    g, t = gemini_status(), tts_status()

    db_ok, db_ms, db_err = False, None, None
    try:
        from config import SessionLocal
        t0 = time.monotonic()
        s = SessionLocal()
        try:
            s.execute(text("SELECT 1"))
            db_ok, db_ms = True, int((time.monotonic() - t0) * 1000)
        finally:
            s.close()
    except Exception as e:
        db_err = str(e)[:200]

    advice = []
    if not g["key_set"]:
        advice.append("GEMINI_API_KEY is missing from backend/.env — Saathi cannot reply.")
    elif g["key_rejected"]:
        advice.append("Google rejected the Gemini key (wrong key, Generative Language API not enabled, or key "
                      "restricted to other APIs/IPs). Create a key at aistudio.google.com and restart.")
    models = g["models_in_order"]
    cooling = g["models_cooling_down"]
    usable = [m for m in models if m not in cooling and m not in g["models_not_found"]]
    if g["key_set"] and not g["key_rejected"] and not usable:
        advice.append("Every Gemini model is out of quota right now. Free-tier daily quotas reset at midnight "
                      "US Pacific (~1:30 PM IST). Use a billed key or a second key for the demo.")
    elif cooling:
        advice.append(f"Out of quota for now: {', '.join(cooling)} — using {usable[0] if usable else 'none'}.")
    if g["models_not_found"]:
        advice.append(f"Model names not available to this key: {', '.join(g['models_not_found'])} — "
                      "fix GEMINI_MODEL in .env.")
    if g["endpoint_override"]:
        advice.append("GEMINI_API_ENDPOINT is set: it is used only for the primary model now; consider removing it.")
    if g["last_latency_s"] and g["last_latency_s"] > 6:
        advice.append(f"Last Gemini reply took {g['last_latency_s']} s — the model or network is slow.")
    if not t["available"]:
        advice.append(f"Cloud TTS is off ({t['reason']}); the browser voice is used instead — fine for a demo.")
    if not db_ok:
        advice.append("Database is not reachable — check DATABASE_URL and that PostgreSQL is running.")

    return {"ok": bool(g["key_set"] and not g["key_rejected"] and usable and db_ok),
            "advice": advice or ["All good."],
            "gemini": g, "tts": t, "database": {"ok": db_ok, "ping_ms": db_ms, "error": db_err}}
