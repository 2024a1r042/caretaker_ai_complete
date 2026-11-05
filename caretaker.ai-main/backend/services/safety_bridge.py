"""
safety_bridge.py — connects what the camera *sees* to what Saathi *says*.

When the fall engine confirms a fall (browser live camera, IP-camera session,
or a simulated demo event):

  1. A SafetyEvent row is stored with the engine's evidence & explanation.
  2. Saathi immediately speaks to the person BY NAME on every open voice-bot
     screen for that recipient:  "Kamla ji, kya aap theek hain? Maine dekha
     aap gir gayi…"  and listens for the answer.
  3. The answer decides what happens:
        "main theek hoon" / "I'm fine"       → resolved_ok, family informed (low urgency)
        "madad" / "dard" / "uth nahi pa rahi" → escalated immediately
        no answer within the window           → escalated
        engine reports LONG LIE               → escalated (critical), whatever was said
        engine reports they GOT UP            → Saathi acknowledges, still asks about pain
  4. Dashboards get live Socket.IO updates; the caregiver gets an email with
     the evidence (and the camera frame when available).

Everything here is thread-safe: camera threads call `report_event(...)`,
which hops onto the FastAPI event loop.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re
import threading
from typing import Callable, Dict, List, Optional, Set

from tables.safety_events import SafetyEvent, SafetyStatusEnum

# ── configuration ────────────────────────────────────────────────────────────
RESPONSE_WINDOW_S = {"high": 30, "medium": 60, "critical": 0}
REASK_AFTER_UNCLEAR = True
NUDGE_COOLDOWN_S = 30 * 60   # at most one coughing check-in per half hour


class SafetyBridge:
    def __init__(self, session_factory: Optional[Callable] = None):
        self._session_factory = session_factory
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._sockets: Dict[int, Set] = {}
        self._lock = threading.Lock()
        self._timers: Dict[int, asyncio.Task] = {}
        self._unclear_count: Dict[int, int] = {}
        # pluggable side-effects (overridden in tests)
        self.email_sender: Optional[Callable] = None     # async (to, subject, html, image_bytes)
        self.sio_emit: Optional[Callable] = None         # async (event, payload)
        self.tts: Optional[Callable] = None              # (text, lang) -> base64
        self.frames: Dict[int, bytes] = {}               # event_id -> jpeg
        self._nudged: Dict = {}

    # ── wiring ──────────────────────────────────────────────────────────────
    def session(self):
        if self._session_factory is None:
            from config import SessionLocal
            self._session_factory = SessionLocal
        return self._session_factory()

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def register(self, recipient_id: int, ws):
        with self._lock:
            self._sockets.setdefault(int(recipient_id), set()).add(ws)

    def unregister(self, ws):
        with self._lock:
            for s in self._sockets.values():
                s.discard(ws)

    def listeners(self, recipient_id: Optional[int]) -> List:
        if recipient_id is None:
            return []
        with self._lock:
            return list(self._sockets.get(int(recipient_id), set()))

    # ── entry point (any thread) ────────────────────────────────────────────
    def report_event(self, event: dict, recipient_id: Optional[int], caretaker_id: Optional[int] = None,
                     source: str = "camera_session", frame_jpeg: Optional[bytes] = None):
        coro = self.handle_engine_event(event, recipient_id, caretaker_id, source, frame_jpeg)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is not None:
            return running.create_task(coro)
        if self._loop is not None and self._loop.is_running():
            return asyncio.run_coroutine_threadsafe(coro, self._loop)
        # no server loop (scripts / tests) — run to completion
        return asyncio.run(coro)

    # ── core handling ───────────────────────────────────────────────────────
    async def handle_engine_event(self, event: dict, recipient_id: Optional[int], caretaker_id: Optional[int],
                                  source: str, frame_jpeg: Optional[bytes] = None) -> Optional[int]:
        etype = event.get("type")
        if etype == "fall_confirmed":
            return await self._on_fall(event, recipient_id, caretaker_id, source, frame_jpeg)
        if etype == "long_lie":
            return await self._on_long_lie(event, recipient_id, caretaker_id, source)
        if etype == "recovered":
            return await self._on_recovered(event, recipient_id)
        return None

    async def _on_fall(self, event, recipient_id, caretaker_id, source, frame_jpeg) -> int:
        db = self.session()
        try:
            name, lang, family = self._persona(db, recipient_id)
            severity = event.get("severity", "high")
            text = self.checkin_text(name, family, event.get("fall_type", "fall"), lang)
            row = SafetyEvent(care_recipient_id=recipient_id, caretaker_id=caretaker_id or self._caretaker_for(db, recipient_id),
                              event_type="fall_confirmed", fall_type=event.get("fall_type"), severity=severity,
                              confidence=event.get("confidence"), source=source, explanation=event.get("explanation"),
                              evidence=event.get("evidence") or [], status=SafetyStatusEnum.awaiting_response,
                              checkin_text=text)
            if source == "upload":
                row.status = SafetyStatusEnum.logged
            db.add(row)
            db.commit()
            db.refresh(row)
            event_id = row.id
        finally:
            db.close()
        if frame_jpeg:
            self.frames[event_id] = frame_jpeg
        if source == "upload":
            return event_id

        await self._emit("safety_event", {"event_id": event_id, "recipient_id": recipient_id, "status": "awaiting_response",
                                          "severity": severity, "fall_type": event.get("fall_type"),
                                          "explanation": event.get("explanation"), "evidence": event.get("evidence"),
                                          "checkin_text": text})
        window = RESPONSE_WINDOW_S.get(severity, 45)
        delivered = await self._push(recipient_id, {
            "type": "safety_checkin", "event_id": event_id, "text": text, "audio_base64": self._speak(text, lang),
            "severity": severity, "fall_type": event.get("fall_type"), "explanation": event.get("explanation"),
            "listen_seconds": window, "family_name": family,
        })
        if delivered == 0:
            # nobody can hear Saathi right now → don't wait for an answer that can't come
            await self.escalate(event_id, "Fall detected and Saathi is not open on any device to check on them.")
        else:
            self._start_timer(event_id, window)
        return event_id

    async def _on_long_lie(self, event, recipient_id, caretaker_id, source) -> Optional[int]:
        db = self.session()
        try:
            row = self._latest_open(db, recipient_id)
            if row is None:
                row = SafetyEvent(care_recipient_id=recipient_id, caretaker_id=caretaker_id or self._caretaker_for(db, recipient_id),
                                  event_type="long_lie", fall_type="long_lie", severity="critical", source=source,
                                  explanation=event.get("explanation"), evidence=event.get("evidence") or [],
                                  status=SafetyStatusEnum.awaiting_response)
                db.add(row)
            else:
                row.severity = "critical"
                row.explanation = (row.explanation or "") + " | " + (event.get("explanation") or "Long lie after fall.")
            row.time_on_ground_s = event.get("time_on_ground_s")
            db.commit()
            db.refresh(row)
            event_id = row.id
        finally:
            db.close()
        await self.escalate(event_id, event.get("explanation") or "Still on the floor and not moving after a fall.",
                            critical=True)
        return event_id

    async def _on_recovered(self, event, recipient_id) -> Optional[int]:
        db = self.session()
        try:
            row = self._latest_open(db, recipient_id, include_resolved=True)
            if row is None:
                return None
            row.recovered_at = dt.datetime.utcnow()
            row.time_on_ground_s = event.get("time_on_ground_s")
            db.commit()
            event_id, status = row.id, row.status
            name, lang, family = self._persona(db, recipient_id)
        finally:
            db.close()
        await self._emit("safety_event", {"event_id": event_id, "recipient_id": recipient_id, "status": status.value,
                                          "recovered": True, "time_on_ground_s": event.get("time_on_ground_s")})
        if status == SafetyStatusEnum.awaiting_response:
            text = (f"{name}, aap uth gaye — shukr hai! Kahin chot toh nahi lagi? Dard ho toh bataiye."
                    if lang != "en" else f"{name}, I can see you're back up — thank goodness. Are you hurt anywhere?")
            await self._push(recipient_id, {"type": "safety_update", "event_id": event_id, "status": "awaiting_response",
                                            "text": text, "audio_base64": self._speak(text, lang), "keep_listening": True})
        return event_id

    # ── the person's answer ─────────────────────────────────────────────────
    @staticmethod
    def classify_response(text: str) -> str:
        t = (text or "").lower().strip()
        if not t:
            return "unclear"
        help_pat = (r"\b(help|madad|bachao|bachaao|ambulance|doctor|hospital|hurt|hurts|pain|injur|bleed|can'?t get up|"
                    r"cannot get up|unable|dard|chot|choat|uth nahi|uth nahin|nahi uth|khoon|saans nahi|chakkar|"
                    r"not ok|not okay|not fine|not alright|theek nahi|thik nahi|theek nahin|thik nahin|"
                    r"call (my )?(son|daughter|family)|bulao|bula do)\b|मदद|बचाओ|दर्द|चोट|उठ नहीं|ठीक नहीं|खून|डॉक्टर|एम्बुलेंस")
        ok_pat = (r"\b(i'?m (fine|ok|okay|alright|good)|i am (fine|ok|okay|alright|good)|(all )?fine|okay|ok|alright|"
                  r"theek hoon|thik hoon|theek hun|thik hun|main theek|mai theek|mai thik|main thik|theek hai|thik hai|"
                  r"sab theek|koi baat nahi|chinta mat|kuch nahi hua|nahi lagi|nahin lagi|haan theek|haan ji theek|"
                  r"no pain|not hurt|didn'?t hurt|don'?t worry)\b|ठीक हूँ|ठीक हूं|ठीक है|सब ठीक|कोई बात नहीं|चोट नहीं")
        # "chot nahi lagi" / "no pain" are OK even though they contain help words
        if re.search(r"(chot|choat|dard|pain|hurt)\s*(nahi|nahin|nhi|not)|no pain|not hurt|didn'?t hurt|चोट नहीं|दर्द नहीं", t):
            return "ok"
        if re.search(help_pat, t):
            return "help"
        if re.search(ok_pat, t):
            return "ok"
        return "unclear"

    async def handle_response(self, event_id: int, text: str) -> dict:
        verdict = self.classify_response(text)
        db = self.session()
        try:
            row = db.query(SafetyEvent).filter(SafetyEvent.id == event_id).first()
            if row is None:
                return {"status": "unknown_event", "reply": ""}
            recipient_id = row.care_recipient_id
            name, lang, family = self._persona(db, recipient_id)
            row.response_text = ((row.response_text + " | ") if row.response_text else "") + (text or "")[:300]
            row.responded_at = dt.datetime.utcnow()
            if verdict == "ok" and row.status == SafetyStatusEnum.awaiting_response:
                row.status = SafetyStatusEnum.resolved_ok
                row.resolved_at = dt.datetime.utcnow()
            elif verdict == "help":
                row.status = SafetyStatusEnum.needs_help
            db.commit()
            status = row.status
        finally:
            db.close()

        fam = family or ("aapke parivaar" if lang != "en" else "your family")
        if verdict == "ok":
            self._cancel_timer(event_id)
            reply = (f"Shukr hai, {name}! Dheere-dheere, aaram se uthiye — koi jaldi nahi. Main {fam} ko bata deta hoon "
                     f"ki aap theek hain. Agar baad mein kahin dard ho toh mujhe zaroor bataiyega."
                     if lang != "en" else
                     f"Thank goodness, {name}. Take your time getting up. I'll let {fam} know you're okay — "
                     f"tell me if anything starts to hurt later.")
            await self._emit("safety_event", {"event_id": event_id, "recipient_id": recipient_id, "status": "resolved_ok",
                                              "response": text})
            await self._notify_family(event_id, ok=True)
            return {"status": status.value, "verdict": verdict, "reply": reply, "audio_base64": self._speak(reply, lang),
                    "keep_listening": False}
        if verdict == "help":
            self._cancel_timer(event_id)
            await self.escalate(event_id, f'They asked for help: "{(text or "")[:120]}"', speak=False)
            reply = (f"Main abhi {fam} ko bula raha hoon, {name}. Aap hilne ki koshish mat kijiye, aaram se lete rahiye — "
                     f"main yahin aapke saath hoon."
                     if lang != "en" else
                     f"I'm calling {fam} right now, {name}. Please don't try to move — stay still, I'm right here with you.")
            return {"status": "escalated", "verdict": verdict, "reply": reply, "audio_base64": self._speak(reply, lang),
                    "keep_listening": True}
        # unclear
        n = self._unclear_count.get(event_id, 0) + 1
        self._unclear_count[event_id] = n
        if n >= 2:
            self._cancel_timer(event_id)
            await self.escalate(event_id, f'Unclear answer after a fall: "{(text or "")[:120]}"', speak=False)
            reply = (f"{name}, main {fam} ko bata raha hoon taaki koi aapko dekh le. Main yahin hoon."
                     if lang != "en" else f"{name}, I'm letting {fam} know so someone can check on you. I'm right here.")
            return {"status": "escalated", "verdict": verdict, "reply": reply, "audio_base64": self._speak(reply, lang),
                    "keep_listening": True}
        reply = (f"{name}, kya aap theek hain? Bas 'theek hoon' boliye, ya 'madad' boliye."
                 if lang != "en" else f"{name}, are you okay? Just say 'I'm fine', or say 'help'.")
        return {"status": status.value, "verdict": verdict, "reply": reply, "audio_base64": self._speak(reply, lang),
                "keep_listening": True}

    # ── escalation ──────────────────────────────────────────────────────────
    async def escalate(self, event_id: int, reason: str, critical: bool = False, speak: bool = True):
        self._cancel_timer(event_id)
        db = self.session()
        try:
            row = db.query(SafetyEvent).filter(SafetyEvent.id == event_id).first()
            if row is None:
                return
            already = row.status == SafetyStatusEnum.escalated
            row.status = SafetyStatusEnum.escalated
            row.escalated_at = row.escalated_at or dt.datetime.utcnow()
            row.escalation_reason = reason if not row.escalation_reason else f"{row.escalation_reason} | {reason}"
            if critical:
                row.severity = "critical"
            db.commit()
            recipient_id = row.care_recipient_id
            name, lang, family = self._persona(db, recipient_id)
        finally:
            db.close()
        await self._emit("safety_event", {"event_id": event_id, "recipient_id": recipient_id, "status": "escalated",
                                          "reason": reason, "critical": critical})
        if speak:
            fam = family or ("aapke parivaar" if lang != "en" else "your family")
            text = (f"{name}, maine {fam} ko khabar kar di hai, madad aa rahi hai. Hilne ki koshish mat kijiye, main yahin hoon."
                    if lang != "en" else
                    f"{name}, I've alerted {fam} and help is on the way. Try not to move — I'm right here.")
            await self._push(recipient_id, {"type": "safety_update", "event_id": event_id, "status": "escalated",
                                            "text": text, "audio_base64": self._speak(text, lang), "keep_listening": True})
        if not already or critical:
            await self._notify_family(event_id, ok=False, reason=reason, critical=critical)

    def _start_timer(self, event_id: int, seconds: float):
        self._cancel_timer(event_id)

        async def _wait():
            try:
                await asyncio.sleep(seconds)
                db = self.session()
                try:
                    row = db.query(SafetyEvent).filter(SafetyEvent.id == event_id).first()
                    pending = row is not None and row.status == SafetyStatusEnum.awaiting_response
                    got_up = row is not None and row.recovered_at is not None
                finally:
                    db.close()
                if pending:
                    why = (f"No answer {int(seconds)} s after the fall (they did get up by themselves)." if got_up
                           else f"No answer {int(seconds)} s after the fall.")
                    await self.escalate(event_id, why)
            except asyncio.CancelledError:
                pass
        try:
            loop = asyncio.get_running_loop()
            self._timers[event_id] = loop.create_task(_wait())
        except RuntimeError:
            pass

    def _cancel_timer(self, event_id: int):
        t = self._timers.pop(event_id, None)
        if t is not None and not t.done():
            t.cancel()

    # ── notifications ───────────────────────────────────────────────────────
    async def _notify_family(self, event_id: int, ok: bool, reason: str = "", critical: bool = False):
        db = self.session()
        try:
            row = db.query(SafetyEvent).filter(SafetyEvent.id == event_id).first()
            if row is None:
                return
            to = self._caretaker_email(db, row.caretaker_id)
            name, _, _ = self._persona(db, row.care_recipient_id)
            ev_rows = "".join(f"<li>{'✔' if e.get('passed') else '•'} {e.get('text', '')}</li>" for e in (row.evidence or []))
            when = row.created_at.strftime("%d %b %Y, %I:%M:%S %p") + " UTC" if row.created_at else ""
            if ok:
                subject = f"Fall detected — {name} says they are OK"
                head = f"<h2 style='color:#b26a00'>Fall detected — {name} answered that they are okay</h2>"
                body_extra = f"<p><b>Their answer:</b> “{row.response_text or ''}”</p><p>Please give them a call when you can.</p>"
            else:
                subject = ("🚨 CRITICAL: " if critical else "🚨 ") + f"{name} may need help — fall detected"
                head = f"<h2 style='color:#c62828'>{'CRITICAL — ' if critical else ''}{name} may need help</h2>"
                body_extra = f"<p><b>Why we are alerting you:</b> {reason}</p>" + \
                             (f"<p><b>Their answer:</b> “{row.response_text}”</p>" if row.response_text else "") + \
                             "<p><b>Please check on them immediately.</b></p>"
            html = f"""<html><body style="font-family:Arial,sans-serif;line-height:1.55">
                <div style="max-width:620px;margin:auto;padding:20px;border:1px solid #eee">{head}
                <p><b>When:</b> {when}<br><b>Type:</b> {(row.fall_type or row.event_type).replace('_', ' ')}
                &nbsp; <b>Confidence:</b> {row.confidence if row.confidence is not None else '-'}</p>
                <p><b>What the camera saw:</b> {row.explanation or ''}</p><ul>{ev_rows}</ul>{body_extra}
                <p style="color:#888;font-size:12px">Saathi checked on {name} by voice before alerting you.</p></div></body></html>"""
            image = self.frames.get(event_id)
        finally:
            db.close()
        if not to:
            return
        try:
            sender = self.email_sender
            if sender is None:
                from utils.email import send_safety_email as sender
            await sender(to, subject, html, image)
        except Exception as e:
            print(f"[safety] email failed: {e}")

    async def _emit(self, name: str, payload: dict):
        try:
            emit = self.sio_emit
            if emit is None:
                from socket_manager import sio_server
                emit = sio_server.emit
            rid = payload.get("recipient_id")
            if rid is not None:
                # only dashboards authenticated for this person receive it
                await emit(name, payload, room=f"recipient_{int(rid)}")
            else:
                await emit(name, payload)
        except Exception as e:
            print(f"[safety] socket emit failed: {e}")

    async def _push(self, recipient_id, payload: dict) -> int:
        n = 0
        for ws in self.listeners(recipient_id):
            try:
                await ws.send_json(payload)
                n += 1
            except Exception:
                self.unregister(ws)
        return n

    def _speak(self, text: str, lang: str) -> str:
        try:
            fn = self.tts
            if fn is None:
                from utils.tts_handler import generate_speech_base64 as fn
            return fn(text, "en-US" if lang == "en" else "hi-IN") or ""
        except Exception:
            return ""

    # ── gentle, non-emergency care nudges (e.g. a coughing fit) ──────────────
    async def care_nudge(self, recipient_id: int, kind: str, detail: str = "") -> int:
        """Saathi says something caring on the person's screen. Rate-limited per kind."""
        import time as _time
        key = (int(recipient_id), kind)
        last = self._nudged.get(key, -1e9)
        if _time.monotonic() - last < NUDGE_COOLDOWN_S:
            return 0
        self._nudged[key] = _time.monotonic()
        db = self.session()
        try:
            name, lang, family = self._persona(db, recipient_id)
            if kind == "coughing_fit":
                text = (f"{name}, aapko kaafi khansi aa rahi hai. Thoda gungunaa paani pee lijiye. "
                        f"Agar saans lene mein dikkat ho ya seene mein dard ho, toh mujhe turant bataiye."
                        if lang != "en" else
                        f"{name}, you've been coughing quite a bit. Would you sip some warm water? "
                        f"If you feel short of breath or any chest pain, tell me straight away.")
                try:
                    import datetime as _dt
                    from services.personalization import upsert_memory
                    upsert_memory(db, recipient_id, "health",
                                  f"Had a coughing fit on {_dt.datetime.now().strftime('%A at %I:%M %p')} ({detail})",
                                  importance=3, source="system",
                                  follow_up_at=_dt.datetime.utcnow() + _dt.timedelta(hours=18))
                except Exception as e:
                    print(f"[safety] could not store cough memory: {e}")
            else:
                text = f"{name}, sab theek hai?" if lang != "en" else f"{name}, is everything alright?"
        finally:
            db.close()
        n = await self._push(recipient_id, {"type": "care_nudge", "kind": kind, "text": text,
                                            "audio_base64": self._speak(text, lang)})
        await self._emit("care_nudge", {"recipient_id": recipient_id, "kind": kind, "text": text, "delivered": n})
        return n

    # ── helpers ─────────────────────────────────────────────────────────────
    @staticmethod
    def checkin_text(name: str, family: Optional[str], fall_type: str, lang: str = "hi") -> str:
        fam = family or ("aapke parivaar" if lang != "en" else "your family")
        if lang == "en":
            seen = "you're on the floor" if fall_type in ("found_on_floor", "slow_collapse") else "you fell"
            return (f"{name}, are you alright? I think {seen}. If you're okay, just say 'I'm fine'. "
                    f"If you need help, say 'help' and I'll call {fam} right away.")
        seen = "aap neeche baithe/lete hain" if fall_type in ("found_on_floor", "slow_collapse") else "aap gir gaye"
        return (f"{name}, kya aap theek hain? Mujhe laga {seen}. Agar aap theek hain toh boliye 'main theek hoon'. "
                f"Madad chahiye toh 'madad' boliye — main turant {fam} ko bulaunga.")

    def _persona(self, db, recipient_id):
        name, lang, family = "ji", "hi", None
        if recipient_id is None:
            return name, lang, family
        try:
            from tables.users import CareRecipient
            from services.personalization import get_or_create_profile, address_name
            rec = db.query(CareRecipient).filter(CareRecipient.id == recipient_id).first()
            prof = get_or_create_profile(db, recipient_id)
            name = address_name(prof, rec.full_name if rec else "")
            lang = "en" if (prof.language_preference or "hi") == "en" else "hi"
            fam = [f for f in (prof.family_members or []) if isinstance(f, dict) and f.get("name")]
            pri = [f for f in fam if f.get("is_emergency_contact")] or fam
            family = pri[0]["name"] if pri else None
        except Exception as e:
            print(f"[safety] persona lookup failed: {e}")
        return name, lang, family

    @staticmethod
    def _caretaker_for(db, recipient_id):
        if recipient_id is None:
            return None
        try:
            from tables.users import CareRecipient
            rec = db.query(CareRecipient).filter(CareRecipient.id == recipient_id).first()
            return rec.caretaker_id if rec else None
        except Exception:
            return None

    @staticmethod
    def _caretaker_email(db, caretaker_id):
        if caretaker_id is None:
            return None
        try:
            from tables.users import CareTaker
            ct = db.query(CareTaker).filter(CareTaker.id == caretaker_id).first()
            return ct.email if ct else None
        except Exception:
            return None

    @staticmethod
    def _latest_open(db, recipient_id, include_resolved=False):
        q = db.query(SafetyEvent).filter(SafetyEvent.care_recipient_id == recipient_id,
                                         SafetyEvent.created_at >= dt.datetime.utcnow() - dt.timedelta(minutes=30))
        statuses = [SafetyStatusEnum.awaiting_response, SafetyStatusEnum.needs_help, SafetyStatusEnum.escalated]
        if include_resolved:
            statuses.append(SafetyStatusEnum.resolved_ok)
        return q.filter(SafetyEvent.status.in_(statuses)).order_by(SafetyEvent.created_at.desc()).first()


safety_bridge = SafetyBridge()
