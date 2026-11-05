"""
Socket.IO manager — live audio classification for the audio monitoring page,
plus live updates (alerts, safety events) for dashboards.

Changes from the original port of coughandsneezedetection/app.py:
  • every client has its own audio buffer and its own episode tracker
    (a single shared buffer used to mix two open tabs together)
  • classifications go only to the client that sent the audio, and alerts only
    to clients authenticated for that same care recipient — previously both were
    broadcast to EVERY connected browser, including other families
  • consecutive windows of one cough are merged into ONE alert / DB row, with
    plain-language reasons; several coughs close together become a "coughing fit"
    and Saathi gently checks in by voice
"""

import datetime
import logging
import time
from typing import Dict

import socketio

from config import SessionLocal
from repository.users import JWTRepo
from services.audio_detection import audio_service
from services.audio_episodes import CoughEpisodeTracker
from tables.audio_events import AudioEvent, AudioEventType

logger = logging.getLogger(__name__)

sio_server = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins="*",
    ping_timeout=60,
    ping_interval=25,
    max_http_buffer_size=1e8
)
sio_app = socketio.ASGIApp(sio_server)

_trackers: Dict[str, CoughEpisodeTracker] = {}


def _room(recipient_id):
    return f"recipient_{int(recipient_id)}"


@sio_server.event
async def connect(sid, environ):
    audio_service.reset_buffer(sid)
    _trackers[sid] = CoughEpisodeTracker()
    logger.info(f"  [+] Client connected: {sid}")
    await sio_server.emit("connection_ack", {"status": "connected"}, room=sid)


@sio_server.event
async def disconnect(sid):
    audio_service.reset_buffer(sid)
    _trackers.pop(sid, None)
    logger.info(f"  [-] Client disconnected: {sid}")


@sio_server.event
async def reset(sid):
    audio_service.reset_buffer(sid)
    _trackers[sid] = CoughEpisodeTracker()
    await sio_server.emit("reset_ack", {"status": "ok",
                                        "timestamp": datetime.datetime.now().strftime("%H:%M:%S")}, room=sid)


@sio_server.event
async def authenticate(sid, data):
    """Receive JWT + care_recipient_id; join that recipient's room if they belong to this caretaker."""
    token = (data or {}).get("token")
    rid = (data or {}).get("care_recipient_id") or (data or {}).get("recipient_id")
    if not token:
        await sio_server.emit("auth_error", {"detail": "Missing token"}, room=sid)
        return
    try:
        payload = JWTRepo.decode_token(token)
        if not payload:
            await sio_server.emit("auth_error", {"detail": "Invalid token"}, room=sid)
            return
        username = payload.get("sub")
        caretaker_id, owned_rid = None, None
        db = SessionLocal()
        try:
            from tables.users import CareTaker, CareRecipient
            ct = db.query(CareTaker).filter(CareTaker.username == username).first()
            caretaker_id = ct.id if ct else None
            if ct and rid:
                rec = db.query(CareRecipient).filter(CareRecipient.id == int(rid),
                                                     CareRecipient.caretaker_id == ct.id).first()
                owned_rid = rec.id if rec else None
        finally:
            db.close()
        await sio_server.save_session(sid, {"username": username, "caretaker_id": caretaker_id,
                                            "care_recipient_id": owned_rid, "authenticated": True})
        if owned_rid:
            await sio_server.enter_room(sid, _room(owned_rid))
        await sio_server.emit("auth_ack", {"status": "authenticated", "recipient_id": owned_rid}, room=sid)
    except Exception as e:
        logger.error(f"Authentication failed for {sid}: {e}")
        await sio_server.emit("auth_error", {"detail": str(e)}, room=sid)


@sio_server.event
async def audio_chunk(sid, data):
    """Raw float32 PCM at 16 kHz → per-window classification → merged events."""
    try:
        results = audio_service.process_audio_chunk(data, sid=sid)
        tracker = _trackers.setdefault(sid, CoughEpisodeTracker())
        session = await sio_server.get_session(sid) or {}
        rid = session.get("care_recipient_id")
        target = _room(rid) if rid else sid
        for result in results:
            await sio_server.emit("classification", result, room=sid)
            for ev in tracker.update(time.monotonic(), result):
                await _publish(sid, session, target, ev)
    except Exception as e:
        logger.error(f"Error processing audio chunk from {sid}: {e}")


async def _publish(sid, session, target, ev):
    now = datetime.datetime.now().strftime("%H:%M:%S")
    if ev["kind"] == "sound":
        await sio_server.emit("alert", {"type": ev["type"], "confidence": ev["confidence"], "timestamp": now,
                                        "why": ev["why"], "duration_s": ev["duration_s"]}, room=target)
        _log_event(session, ev)
    elif ev["kind"] == "fit":
        rid = session.get("care_recipient_id")
        delivered = 0
        if rid:
            try:
                from services.safety_bridge import safety_bridge
                delivered = await safety_bridge.care_nudge(rid, "coughing_fit", detail=ev["why"][0])
            except Exception as e:
                logger.error(f"care nudge failed: {e}")
        await sio_server.emit("audio_episode", {"type": "coughing_fit", "coughs": ev["coughs"], "span_s": ev["span_s"],
                                                "timestamp": now, "why": ev["why"],
                                                "saathi_checked_in": delivered > 0}, room=target)


def _log_event(session, ev):
    """One row per real cough/sneeze (not per overlapping window)."""
    if not session.get("authenticated") or not session.get("caretaker_id"):
        return
    db = SessionLocal()
    try:
        db.add(AudioEvent(caretaker_id=session["caretaker_id"], care_recipient_id=session.get("care_recipient_id"),
                          event_type=AudioEventType(ev["type"]), confidence=ev["confidence"],
                          duration_ms=int(ev["duration_s"] * 1000), notes=", ".join(ev["why"])[:250] or None))
        db.commit()
    except Exception as e:
        logger.error(f"DB logging failed: {e}")
        db.rollback()
    finally:
        db.close()
