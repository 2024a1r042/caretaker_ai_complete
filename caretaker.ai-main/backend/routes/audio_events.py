from fastapi import APIRouter, HTTPException, Depends, Query, Header
from sqlalchemy.orm import Session
from config import get_db
from tables.audio_events import AudioEvent, AudioEventType
from tables.users import CareTaker
from repository.users import UsersRepo, JWTRepo
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta

router = APIRouter()


# Authentication helper
def _get_username_from_auth(auth_header: Optional[str]):
    if not auth_header:
        return None
    try:
        parts = auth_header.split()
        if len(parts) != 2:
            return None
        token = parts[1]
        decoded = JWTRepo.decode_token(token)
        return decoded.get('sub') if isinstance(decoded, dict) else None
    except Exception:
        return None


# ── Pydantic Models ──────────────────────────────────────────────────

class AudioEventCreate(BaseModel):
    """Schema for creating a new audio event"""
    care_recipient_id: Optional[int] = None
    event_type: str  # "Cough", "Sneeze", "Talking", "Noise"
    confidence: float  # 0.0 to 100.0
    duration_ms: Optional[int] = None
    notes: Optional[str] = None


class AudioEventResponse(BaseModel):
    """Schema for audio event response"""
    id: int
    caretaker_id: int
    care_recipient_id: Optional[int]
    event_type: str
    confidence: float
    detected_at: datetime
    duration_ms: Optional[int]
    notes: Optional[str]

    class Config:
        from_attributes = True


class AudioEventStats(BaseModel):
    """Statistics for audio events"""
    total_events: int
    cough_count: int
    sneeze_count: int
    talking_count: int
    noise_count: int
    date_range: str


# ── API Endpoints ────────────────────────────────────────────────────

@router.post("/audio-events", response_model=AudioEventResponse)
async def create_audio_event(
    event: AudioEventCreate,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Create a new audio event (cough, sneeze, etc.)
    """
    # Authenticate
    username = _get_username_from_auth(authorization)
    if not username:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    current_user = UsersRepo.find_by_username(db, CareTaker, username)
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        # Validate event type
        event_type_enum = AudioEventType[event.event_type.lower()]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid event type: {event.event_type}")
    
    # Validate confidence range
    if not (0.0 <= event.confidence <= 100.0):
        raise HTTPException(status_code=400, detail="Confidence must be between 0 and 100")
    
    # Create new audio event
    db_event = AudioEvent(
        caretaker_id=current_user.id,
        care_recipient_id=event.care_recipient_id,
        event_type=event_type_enum,
        confidence=event.confidence,
        duration_ms=event.duration_ms,
        notes=event.notes
    )
    
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    
    return db_event


@router.get("/audio-events", response_model=List[AudioEventResponse])
async def get_audio_events(
    care_recipient_id: Optional[int] = Query(None, description="Filter by care recipient ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type (Cough, Sneeze, etc.)"),
    days: int = Query(7, description="Number of days to look back"),
    limit: int = Query(100, description="Maximum number of events to return"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Get audio events for the current caretaker with optional filters
    """
    # Authenticate
    username = _get_username_from_auth(authorization)
    if not username:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    current_user = UsersRepo.find_by_username(db, CareTaker, username)
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    # Build query
    query = db.query(AudioEvent).filter(AudioEvent.caretaker_id == current_user.id)
    
    # Apply filters
    if care_recipient_id:
        query = query.filter(AudioEvent.care_recipient_id == care_recipient_id)
    
    if event_type:
        try:
            event_type_enum = AudioEventType[event_type.lower()]
            query = query.filter(AudioEvent.event_type == event_type_enum)
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid event type: {event_type}")
    
    # Filter by date range
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    query = query.filter(AudioEvent.detected_at >= cutoff_date)
    
    # Order by most recent first and limit
    query = query.order_by(AudioEvent.detected_at.desc()).limit(limit)
    
    events = query.all()
    return events


@router.get("/audio-events/stats", response_model=AudioEventStats)
async def get_audio_event_stats(
    care_recipient_id: Optional[int] = Query(None, description="Filter by care recipient ID"),
    days: int = Query(7, description="Number of days to analyze"),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Get statistics for audio events over a specified time period
    """
    # Authenticate
    username = _get_username_from_auth(authorization)
    if not username:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    current_user = UsersRepo.find_by_username(db, CareTaker, username)
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    # Build base query
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    query = db.query(AudioEvent).filter(
        AudioEvent.caretaker_id == current_user.id,
        AudioEvent.detected_at >= cutoff_date
    )
    
    # Apply recipient filter if provided
    if care_recipient_id:
        query = query.filter(AudioEvent.care_recipient_id == care_recipient_id)
    
    # Get all events
    events = query.all()
    
    # Calculate statistics
    total_events = len(events)
    cough_count = sum(1 for e in events if e.event_type == AudioEventType.cough)
    sneeze_count = sum(1 for e in events if e.event_type == AudioEventType.sneeze)
    talking_count = sum(1 for e in events if e.event_type == AudioEventType.talking)
    noise_count = sum(1 for e in events if e.event_type == AudioEventType.noise)
    
    date_range = f"Last {days} days"
    
    return AudioEventStats(
        total_events=total_events,
        cough_count=cough_count,
        sneeze_count=sneeze_count,
        talking_count=talking_count,
        noise_count=noise_count,
        date_range=date_range
    )


@router.delete("/audio-events/{event_id}")
async def delete_audio_event(
    event_id: int,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Delete a specific audio event
    """
    # Authenticate
    username = _get_username_from_auth(authorization)
    if not username:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    
    current_user = UsersRepo.find_by_username(db, CareTaker, username)
    if not current_user:
        raise HTTPException(status_code=404, detail="User not found")
    event = db.query(AudioEvent).filter(
        AudioEvent.id == event_id,
        AudioEvent.caretaker_id == current_user.id
    ).first()
    
    if not event:
        raise HTTPException(status_code=404, detail="Audio event not found")
    
    db.delete(event)
    db.commit()
    
    return {"message": "Audio event deleted successfully"}


@router.get("/audio-events/summary")
async def get_audio_summary(
    care_recipient_id: Optional[int] = Query(None),
    days: int = Query(7, ge=2, le=31),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Today vs. their usual — the comparison a family actually needs:
    per-day counts, today's hourly pattern, and recent events with the reasons
    the classifier gave. Times are in the server's local time zone.
    """
    username = _get_username_from_auth(authorization)
    if not username:
        raise HTTPException(status_code=401, detail="Missing or invalid token")
    user = UsersRepo.find_by_username(db, CareTaker, username)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    offset = datetime.now() - datetime.utcnow()          # stored UTC → local
    local_now = datetime.now()
    start_local = (local_now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    q = db.query(AudioEvent).filter(AudioEvent.caretaker_id == user.id,
                                    AudioEvent.detected_at >= start_local - offset)
    if care_recipient_id:
        q = q.filter(AudioEvent.care_recipient_id == care_recipient_id)
    rows = q.order_by(AudioEvent.detected_at.desc()).all()

    daily = {}
    for i in range(days):
        d = (start_local + timedelta(days=i)).date()
        daily[d] = {"date": d.isoformat(), "cough": 0, "sneeze": 0}
    hourly = [0] * 24
    today = local_now.date()
    for r in rows:
        lt = r.detected_at + offset
        key = "cough" if r.event_type == AudioEventType.cough else "sneeze" if r.event_type == AudioEventType.sneeze else None
        if key and lt.date() in daily:
            daily[lt.date()][key] += 1
            if key == "cough" and lt.date() == today:
                hourly[lt.hour] += 1

    series = list(daily.values())
    today_row = series[-1]
    past = series[:-1]
    usual = round(sum(d["cough"] for d in past) / len(past), 1) if past else 0.0
    t = today_row["cough"]
    if t == 0:
        comparison = "No coughs heard today."
    elif usual < 1:
        comparison = f"{t} cough{'s' if t != 1 else ''} today — more than usual (almost none on recent days)."
    else:
        ratio = t / usual
        if ratio >= 1.8:
            comparison = f"{t} coughs today — about {ratio:.1f}× the usual {usual:g} a day."
        elif ratio <= 0.6:
            comparison = f"{t} coughs today — fewer than the usual {usual:g} a day."
        else:
            comparison = f"{t} coughs today — about the same as usual ({usual:g} a day)."

    recent = [{"type": r.event_type.value, "confidence": r.confidence,
               "at": (r.detected_at + offset).isoformat(timespec="seconds"), "why": r.notes or ""}
              for r in rows[:15]]
    return {"today": today_row, "usual_cough_per_day": usual, "comparison": comparison,
            "daily": series, "hourly_today": hourly, "recent": recent}
