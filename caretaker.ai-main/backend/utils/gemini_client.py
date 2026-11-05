"""
Central Gemini API client.

Configure via .env:
    GEMINI_API_KEY=<your key>
    GEMINI_MODEL=gemini-3.1-flash-lite          # primary model (largest free daily quota per your notes)
    GEMINI_FALLBACK_MODELS=gemini-2.5-flash      # optional, comma-separated
    GEMINI_API_ENDPOINT=<optional full URL>      # only used for the PRIMARY model

WHY THIS WAS REWRITTEN
----------------------
The old client retried 3 models x 3 attempts with 2 s + 4 s sleeps on every
429. When the free-tier DAILY quota was used up (it can never succeed until
the next day), each call still burned ~18 s and 9 requests before giving up —
and Saathi made two such calls per message (~40 s, then an apology).

Now:
  • 429 is classified from Google's error details:
      – per-DAY quota  → model is skipped until the quota resets (midnight Pacific)
      – per-MINUTE     → honour Google's retryDelay; wait only if it is tiny,
                         otherwise skip the model for that long
  • invalid / unauthorised key → fail instantly (and say so clearly), no retries
  • 404 model → never tried again this run
  • every call has ONE total time budget (`timeout`), shared across fallbacks
  • models already known to be exhausted are skipped without any network call
  • one keep-alive HTTPS session (saves a TLS handshake per request)
  • `fast=True` turns off "thinking" on 2.5-Flash models (seconds faster for chat)
  • `gemini_status()` reports key / quota / cooldown state for /api/health/ai
"""

import copy
import datetime as _dt
import json
import os
import re
import threading
import time

import requests

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

DEFAULT_MODEL = "gemini-3.1-flash-lite"
FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]

_session = requests.Session()
_lock = threading.Lock()
_cooldown_until: dict = {}        # model -> unix time it may be tried again
_cooldown_reason: dict = {}
_missing_models: set = set()
_key_state = {"fingerprint": None, "invalid": False, "reason": ""}
_last_skip_log = 0.0
_stats = {"last_ok_model": None, "last_ok_at": None, "last_latency_s": None, "last_error": None,
          "last_error_at": None, "calls": 0, "failures": 0}


def safe_json_parse(text: str) -> dict | None:
    """
    Tries to parse text as JSON. If it fails, uses regex to extract
    the first JSON block { ... } and parses that.
    """
    if not text:
        return None
    try:
        clean_text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception:
        pass
    try:
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────
def _fingerprint(key: str) -> str:
    return f"{key[:4]}…{key[-4:]}" if len(key) > 8 else "set"


def _models_to_try(model_override: str | None) -> list:
    primary = model_override or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)
    extra = [m.strip() for m in os.environ.get("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()]
    out = []
    for m in [primary] + extra + FALLBACK_MODELS:
        if m and m not in out:
            out.append(m)
    return out


def get_gemini_url(model: str, api_key: str, primary: bool = True) -> str:
    endpoint = os.environ.get("GEMINI_API_ENDPOINT")
    # The override URL hard-codes one model, so it must not be reused for the
    # fallbacks — otherwise "fallback" just re-hits the same failing model.
    if endpoint and primary:
        return f"{endpoint}?key={api_key}"
    return f"{BASE_URL}/{model}:generateContent?key={api_key}"


def _next_pacific_midnight_ts() -> float:
    """Gemini daily quotas reset at midnight US Pacific time."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("America/Los_Angeles")
        now = _dt.datetime.now(tz)
        nxt = (now + _dt.timedelta(days=1)).replace(hour=0, minute=1, second=0, microsecond=0)
        return nxt.timestamp()
    except Exception:
        return time.time() + 3600


def _classify_429(resp) -> tuple:
    """Returns ('day'|'minute', retry_after_seconds, message)."""
    msg, retry, per_day = "", None, False
    try:
        err = resp.json().get("error", {})
        msg = err.get("message", "") or ""
        for d in err.get("details", []) or []:
            t = d.get("@type", "")
            if t.endswith("RetryInfo"):
                m = re.match(r"([\d.]+)s", str(d.get("retryDelay", "")))
                if m:
                    retry = float(m.group(1))
            if t.endswith("QuotaFailure"):
                for v in d.get("violations", []) or []:
                    q = (v.get("quotaId", "") + " " + v.get("quotaMetric", "")).lower()
                    if "perday" in q or "per_day" in q or "daily" in q:
                        per_day = True
    except Exception:
        msg = (getattr(resp, "text", "") or "")[:300]
    low = msg.lower()
    if "per day" in low or "perday" in low or "daily" in low:
        per_day = True
    return ("day" if per_day else "minute"), retry, msg[:300]


def _is_key_error(status: int, text: str) -> bool:
    t = (text or "").lower()
    return (status in (401, 403) or
            (status == 400 and ("api_key_invalid" in t or "api key not valid" in t or "api key expired" in t)))


def _cool(model: str, until_ts: float, reason: str):
    with _lock:
        _cooldown_until[model] = max(_cooldown_until.get(model, 0), until_ts)
        _cooldown_reason[model] = reason


def _available(model: str) -> bool:
    with _lock:
        return model not in _missing_models and _cooldown_until.get(model, 0) <= time.time()


def _record_error(err: str):
    with _lock:
        _stats["last_error"], _stats["last_error_at"] = err, time.time()


def _prepare_payload(payload: dict, model: str, fast: bool) -> dict:
    if not fast or not model.startswith("gemini-2.5-flash"):
        return payload
    p = copy.deepcopy(payload)
    gc = p.setdefault("generationConfig", {})
    # 2.5 Flash "thinks" by default (adds seconds); a chat reply doesn't need it.
    gc.setdefault("thinkingConfig", {"thinkingBudget": 0})
    return p


# ─────────────────────────────────────────────────────────────────────────────
# main entry point
# ─────────────────────────────────────────────────────────────────────────────
def call_gemini(payload: dict, timeout: int = 30, caller: str = "", model_override: str = None,
                fast: bool = False) -> dict | None:
    """
    POST `payload` to Gemini, falling back across models, within ONE total
    time budget of `timeout` seconds. Returns the JSON response or None.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print(f"{caller} [Gemini] GEMINI_API_KEY is not set in .env — AI features are off.")
        _record_error("GEMINI_API_KEY not set")
        return None

    fp = _fingerprint(api_key)
    with _lock:
        if _key_state["fingerprint"] != fp:          # key changed → forget old verdicts
            _key_state.update(fingerprint=fp, invalid=False, reason="")
            _cooldown_until.clear()
            _cooldown_reason.clear()
        if _key_state["invalid"]:
            return None
        _stats["calls"] += 1

    deadline = time.monotonic() + max(3.0, float(timeout))
    models = _models_to_try(model_override)
    tried_any = False

    for idx, model in enumerate(models):
        if not _available(model):
            continue
        attempts = 0
        while attempts < 2:
            remaining = deadline - time.monotonic()
            if remaining < 1.5:
                print(f"{caller} [Gemini] time budget ({timeout}s) used up.")
                _record_error("time budget exceeded")
                with _lock:
                    _stats["failures"] += 1
                return None
            attempts += 1
            tried_any = True
            t0 = time.monotonic()
            try:
                resp = _session.post(get_gemini_url(model, api_key, primary=(idx == 0)),
                                     json=_prepare_payload(payload, model, fast),
                                     headers={"Content-Type": "application/json"},
                                     timeout=min(remaining, float(timeout)))
            except requests.exceptions.Timeout:
                print(f"{caller} [Gemini] '{model}' timed out — trying next model.")
                _record_error(f"timeout on {model}")
                _cool(model, time.time() + 30, "timed out")
                break
            except Exception as e:
                print(f"{caller} [Gemini] network error on '{model}': {e}")
                _record_error(f"network error: {e}")
                if attempts < 2:
                    time.sleep(min(0.5, max(0.0, deadline - time.monotonic() - 1.5)))
                    continue
                break

            status = resp.status_code
            if status == 200:
                with _lock:
                    _stats.update(last_ok_model=model, last_ok_at=time.time(),
                                  last_latency_s=round(time.monotonic() - t0, 2))
                if idx > 0:
                    print(f"{caller} [Gemini] answered by fallback model '{model}'.")
                return resp.json()

            text = resp.text[:400] if hasattr(resp, "text") else ""
            if _is_key_error(status, text):
                with _lock:
                    _key_state.update(invalid=True, reason=f"HTTP {status}: {text[:160]}")
                print(f"{caller} [Gemini] API KEY REJECTED (HTTP {status}). Check GEMINI_API_KEY in .env "
                      f"(wrong key, API not enabled, or key restricted). No further calls until the key changes.")
                _record_error(f"key rejected: HTTP {status}")
                return None

            if status == 429:
                kind, retry, msg = _classify_429(resp)
                if kind == "day":
                    _cool(model, _next_pacific_midnight_ts(), "daily quota used up")
                    print(f"{caller} [Gemini] '{model}': DAILY quota used up — skipping it until it resets.")
                    _record_error(f"daily quota exhausted on {model}")
                    break
                wait = retry if retry is not None else 20.0
                if wait <= 3.0 and attempts < 2 and deadline - time.monotonic() > wait + 2:
                    time.sleep(wait)
                    continue
                _cool(model, time.time() + wait, "per-minute rate limit")
                print(f"{caller} [Gemini] '{model}': rate-limited, skipping it for {wait:.0f}s.")
                _record_error(f"rate limited on {model}")
                break

            if status == 404:
                with _lock:
                    _missing_models.add(model)
                print(f"{caller} [Gemini] model '{model}' does not exist for this key — removed from rotation.")
                _record_error(f"model not found: {model}")
                break

            if status in (500, 503) and attempts < 2 and deadline - time.monotonic() > 3:
                time.sleep(0.8)
                continue
            if status in (500, 503):
                _cool(model, time.time() + 30, f"HTTP {status} (overloaded)")
            print(f"{caller} [Gemini] HTTP {status} on '{model}': {text[:200]}")
            _record_error(f"HTTP {status} on {model}")
            break

    with _lock:
        _stats["failures"] += 1
    if not tried_any:
        global _last_skip_log
        if time.time() - _last_skip_log > 60:   # say it once a minute, not on every call
            _last_skip_log = time.time()
            print(f"{caller} [Gemini] every model is cooling down (quota) — skipping calls; see /api/health/ai")
    return None


def gemini_status() -> dict:
    """Snapshot for the /api/health/ai endpoint."""
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    now = time.time()
    with _lock:
        cooling = {m: {"seconds_left": int(t - now), "reason": _cooldown_reason.get(m, "")}
                   for m, t in _cooldown_until.items() if t > now}
        return {
            "key_set": bool(key),
            "key_fingerprint": _fingerprint(key) if key else None,
            "key_rejected": _key_state["invalid"],
            "key_rejected_reason": _key_state["reason"] or None,
            "models_in_order": _models_to_try(None),
            "models_cooling_down": cooling,
            "models_not_found": sorted(_missing_models),
            "endpoint_override": bool(os.environ.get("GEMINI_API_ENDPOINT")),
            "last_ok_model": _stats["last_ok_model"],
            "last_ok_seconds_ago": int(now - _stats["last_ok_at"]) if _stats["last_ok_at"] else None,
            "last_latency_s": _stats["last_latency_s"],
            "last_error": _stats["last_error"],
            "calls": _stats["calls"], "failures": _stats["failures"],
        }


def get_embedding(text: str, model: str = "text-embedding-004") -> list[float] | None:
    """Vector embedding for a piece of text."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key or _key_state["invalid"]:
        return None
    url = f"{BASE_URL}/{model}:embedContent?key={api_key}"
    payload = {"model": f"models/{model}", "content": {"parts": [{"text": text}]}}
    try:
        resp = _session.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("embedding", {}).get("values")
        return None
    except Exception as e:
        print(f"[Embedding] Error: {e}")
        return None
