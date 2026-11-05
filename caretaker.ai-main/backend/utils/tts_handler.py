"""
Google Cloud Text-to-Speech for Saathi's voice.

Setup (separate from GEMINI_API_KEY!):
    1. Enable "Cloud Text-to-Speech API" + billing on a Google Cloud project
    2. Create a service-account key (JSON)
    3. In .env:  GOOGLE_APPLICATION_CREDENTIALS=C:/path/to/key.json

If it is not set up, this module returns "" immediately and the voice-bot page
falls back to the browser's own speech synthesis.

WHY THIS WAS REWRITTEN
----------------------
Before: a brand-new TTS client was created for every reply, and when no
credentials were configured each call first went hunting for Google
credentials (env var → gcloud config → cloud metadata server) before failing —
only billing errors switched it off. That cost time on every single message.
Now: credentials are checked once, the client is created once, auth/billing
failures switch TTS off for the session, each request has a 6 s timeout, and
recent phrases (greetings, check-ins) are cached.
"""

import base64
import os
import threading
from collections import OrderedDict

from dotenv import load_dotenv

load_dotenv()

_lock = threading.Lock()
_client = None
_tts_unavailable = False          # circuit breaker for the whole session
_reason = ""
_cache: "OrderedDict[tuple, str]" = OrderedDict()
_CACHE_MAX = 64
_REQUEST_TIMEOUT_S = 6.0


def _disable(reason: str):
    global _tts_unavailable, _reason
    _tts_unavailable, _reason = True, reason
    print(f"[TTS] Cloud TTS off for this session: {reason}. The browser voice will be used instead.")


def _get_client():
    global _client
    if _client is not None or _tts_unavailable:
        return _client
    with _lock:
        if _client is not None or _tts_unavailable:
            return _client
        creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        if not creds and os.getenv("TTS_USE_ADC", "") != "1":
            _disable("GOOGLE_APPLICATION_CREDENTIALS is not set in .env")
            return None
        if creds and not os.path.isfile(creds):
            _disable(f"credentials file not found: {creds}")
            return None
        try:
            from google.cloud import texttospeech  # lazy: a missing package must not break the voice bot
            _client = texttospeech.TextToSpeechClient()
        except Exception as e:
            _disable(f"could not create client ({type(e).__name__}: {e})")
            return None
    return _client


def generate_speech_base64(text: str, language_code: str = "hi-IN") -> str:
    if _tts_unavailable or not (text or "").strip():
        return ""
    key = (text, language_code)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    client = _get_client()
    if client is None:
        return ""
    try:
        from google.cloud import texttospeech
        voice_name = "hi-IN-Neural2-A" if language_code.startswith("hi") else "en-US-Neural2-F"
        response = client.synthesize_speech(
            input=texttospeech.SynthesisInput(text=text),
            voice=texttospeech.VoiceSelectionParams(language_code=language_code, name=voice_name),
            audio_config=texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3,
                                                  speaking_rate=1.0, pitch=0.0),
            timeout=_REQUEST_TIMEOUT_S,
        )
        audio = base64.b64encode(response.audio_content).decode("utf-8")
        with _lock:
            _cache[key] = audio
            while len(_cache) > _CACHE_MAX:
                _cache.popitem(last=False)
        return audio
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        if any(w in low for w in ("403", "permission", "billing", "has not been used", "disabled",
                                  "unauthenticated", "credentials", "401")):
            _disable(f"{type(e).__name__}: {msg[:160]}")
        else:
            print(f"[TTS Error] {type(e).__name__}: {msg[:200]}")
        return ""


def tts_status() -> dict:
    return {"available": not _tts_unavailable,
            "reason": _reason or None,
            "credentials_env_set": bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS")),
            "client_ready": _client is not None,
            "cached_phrases": len(_cache)}


def is_hindi(text: str) -> bool:
    """Detects if text contains Devanagari characters."""
    return any("\u0900" <= char <= "\u097f" for char in text)
