"""
Safety routes — fall events from any source, their evidence, and the
voice check-in outcome.

POST /api/video-monitoring/log-event      browser live monitor reports engine events (this route was missing → 404)
GET  /api/safety/events/{recipient_id}    history with evidence + outcome
POST /api/safety/events/{id}/respond      REST fallback for the person's answer
POST /api/safety/events/{id}/acknowledge  caregiver marks it handled
POST /api/safety/simulate/{recipient_id}  rehearse the check-in flow without falling (clearly labelled "simulated")
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from config import get_db
from services.safety_bridge import safety_bridge
from tables.safety_events import SafetyEvent, SafetyStatusEnum
from tables.users import CareRecipient, CareTaker

router = APIRouter(tags=["Safety"])


def _caretaker(authorization: Optional[str], db: Session) -> CareTaker:
    from repository.users import JWTRepo
    if not authorization or len(authorization.split()) != 2:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid token")
    try:
        payload = JWTRepo.decode_token(authorization.split()[1])
        username = payload.get("sub") if isinstance(payload, dict) else None
    except Exception:
        username = None
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    ct = db.query(CareTaker).filter(CareTaker.username == username).first()
    if not ct:
        raise HTTPException(status_code=404, detail="User not found")
    return ct


def _own_recipient(db: Session, ct: CareTaker, recipient_id: Optional[int]) -> Optional[CareRecipient]:
    if recipient_id is None:
        return None
    rec = db.query(CareRecipient).filter(CareRecipient.id == int(recipient_id),
                                         CareRecipient.caretaker_id == ct.id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return rec


def _row(e: SafetyEvent) -> dict:
    return {
        "id": e.id, "recipient_id": e.care_recipient_id, "event_type": e.event_type, "fall_type": e.fall_type,
        "severity": e.severity, "confidence": e.confidence, "source": e.source, "explanation": e.explanation,
        "evidence": e.evidence or [], "status": e.status.value if e.status else None,
        "checkin_text": e.checkin_text, "response_text": e.response_text, "escalation_reason": e.escalation_reason,
        "time_on_ground_s": e.time_on_ground_s,
        "created_at": e.created_at.isoformat() + "Z" if e.created_at else None,
        "responded_at": e.responded_at.isoformat() + "Z" if e.responded_at else None,
        "recovered_at": e.recovered_at.isoformat() + "Z" if e.recovered_at else None,
        "escalated_at": e.escalated_at.isoformat() + "Z" if e.escalated_at else None,
    }


class LogEventRequest(BaseModel):
    type: str = "fall"
    timestamp: Optional[str] = None
    confidence: Optional[float] = None
    source: str = "browser_live"
    recipient_id: Optional[int] = None
    event: Optional[Dict[str, Any]] = None      # full engine event (type, fall_type, evidence, explanation…)


@router.post("/video-monitoring/log-event")
async def log_event(req: LogEventRequest, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    ct = _caretaker(authorization, db)
    _own_recipient(db, ct, req.recipient_id)
    ev = dict(req.event or {})
    if not ev.get("type"):
        ev["type"] = {"fall": "fall_confirmed", "long_lie": "long_lie", "recovered": "recovered"}.get(req.type, req.type)
    if req.confidence is not None and "confidence" not in ev:
        ev["confidence"] = req.confidence
    ev.setdefault("severity", "high")
    event_id = await safety_bridge.handle_engine_event(ev, req.recipient_id, ct.id, req.source)
    return {"status": "success", "event_id": event_id}


@router.get("/safety/events/{recipient_id}")
async def list_events(recipient_id: int, limit: int = 20, authorization: Optional[str] = Header(None),
                      db: Session = Depends(get_db)):
    ct = _caretaker(authorization, db)
    _own_recipient(db, ct, recipient_id)
    rows = db.query(SafetyEvent).filter(SafetyEvent.care_recipient_id == recipient_id) \
        .order_by(desc(SafetyEvent.created_at)).limit(max(1, min(limit, 100))).all()
    return {"status": "success", "events": [_row(r) for r in rows]}


class RespondRequest(BaseModel):
    text: str


@router.post("/safety/events/{event_id}/respond")
async def respond(event_id: int, req: RespondRequest, authorization: Optional[str] = Header(None),
                  db: Session = Depends(get_db)):
    ct = _caretaker(authorization, db)
    row = db.query(SafetyEvent).filter(SafetyEvent.id == event_id).first()
    if not row or (row.caretaker_id and row.caretaker_id != ct.id):
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "success", **(await safety_bridge.handle_response(event_id, req.text))}


@router.post("/safety/events/{event_id}/acknowledge")
async def acknowledge(event_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    ct = _caretaker(authorization, db)
    row = db.query(SafetyEvent).filter(SafetyEvent.id == event_id).first()
    if not row or (row.caretaker_id and row.caretaker_id != ct.id):
        raise HTTPException(status_code=404, detail="Event not found")
    safety_bridge._cancel_timer(event_id)
    row.status = SafetyStatusEnum.acknowledged
    row.resolved_at = datetime.utcnow()
    db.commit()
    return {"status": "success", "event": _row(row)}


class SimulateRequest(BaseModel):
    fall_type: str = "hard_fall"
    severity: str = "high"


@router.post("/safety/simulate/{recipient_id}")
async def simulate(recipient_id: int, req: SimulateRequest = SimulateRequest(),
                   authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Rehearsal only — runs the real check-in/escalation flow with a clearly labelled simulated event."""
    ct = _caretaker(authorization, db)
    _own_recipient(db, ct, recipient_id)
    ev = {"type": "fall_confirmed", "fall_type": req.fall_type, "severity": req.severity, "confidence": 0.9,
          "explanation": "SIMULATED event for rehearsal — no camera data.",
          "evidence": [{"signal": "simulated", "passed": True, "text": "Simulated by caregiver (rehearsal)"}]}
    event_id = await safety_bridge.handle_engine_event(ev, recipient_id, ct.id, "simulated")
    return {"status": "success", "event_id": event_id}
