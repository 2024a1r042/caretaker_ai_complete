"""
Personalization routes — the family tells Saathi who their parent is, and
can see / correct everything Saathi has learned.

GET    /api/personalization/{rid}/profile
PUT    /api/personalization/{rid}/profile
GET    /api/personalization/{rid}/memories
POST   /api/personalization/{rid}/memories
DELETE /api/personalization/{rid}/memories/{mid}
GET    /api/personalization/{rid}/context-preview   what Saathi knows right now + its next proactive opener
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from config import get_db
from services import personalization as P
from tables.personalization import RecipientMemory
from tables.users import CareRecipient, CareTaker

router = APIRouter(tags=["Personalization"], prefix="/personalization")


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


def _recipient(db: Session, authorization: Optional[str], rid: int) -> CareRecipient:
    ct = _caretaker(authorization, db)
    rec = db.query(CareRecipient).filter(CareRecipient.id == rid, CareRecipient.caretaker_id == ct.id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recipient not found")
    return rec


def _mem(m: RecipientMemory) -> dict:
    return {"id": m.id, "category": m.category.value, "content": m.content, "importance": m.importance,
            "source": m.source, "mention_count": m.mention_count,
            "follow_up_at": m.follow_up_at.isoformat() + "Z" if m.follow_up_at else None,
            "followed_up": m.followed_up,
            "first_mentioned_at": m.first_mentioned_at.isoformat() + "Z" if m.first_mentioned_at else None,
            "last_mentioned_at": m.last_mentioned_at.isoformat() + "Z" if m.last_mentioned_at else None}


@router.get("/{rid}/profile")
async def get_profile(rid: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    rec = _recipient(db, authorization, rid)
    prof = P.get_or_create_profile(db, rid)
    return {"status": "success", "recipient": {"id": rec.id, "full_name": rec.full_name, "age": rec.age,
                                               "city": rec.city},
            "profile": P.profile_to_dict(prof)}


class ProfileUpdate(BaseModel):
    preferred_name: Optional[str] = None
    language_preference: Optional[str] = None
    native_language: Optional[str] = None
    hometown: Optional[str] = None
    former_occupation: Optional[str] = None
    faith: Optional[str] = None
    dietary_notes: Optional[str] = None
    conversation_style: Optional[str] = None
    wake_time: Optional[str] = None
    sleep_time: Optional[str] = None
    favorite_foods: Optional[List[str]] = None
    disliked_foods: Optional[List[str]] = None
    favorite_music: Optional[List[str]] = None
    favorite_shows: Optional[List[str]] = None
    hobbies: Optional[List[str]] = None
    family_members: Optional[List[Dict[str, Any]]] = None
    important_dates: Optional[List[Dict[str, Any]]] = None
    daily_routine: Optional[List[Dict[str, Any]]] = None
    life_stories: Optional[List[str]] = None
    topics_to_avoid: Optional[List[str]] = None


@router.put("/{rid}/profile")
async def put_profile(rid: int, body: ProfileUpdate, authorization: Optional[str] = Header(None),
                      db: Session = Depends(get_db)):
    _recipient(db, authorization, rid)
    data = body.model_dump(exclude_unset=True) if hasattr(body, "model_dump") else body.dict(exclude_unset=True)
    prof = P.update_profile(db, rid, data)
    return {"status": "success", "profile": P.profile_to_dict(prof)}


@router.get("/{rid}/memories")
async def list_memories(rid: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    _recipient(db, authorization, rid)
    rows = db.query(RecipientMemory).filter(RecipientMemory.care_recipient_id == rid,
                                            RecipientMemory.active == True) \
        .order_by(desc(RecipientMemory.last_mentioned_at)).limit(200).all()  # noqa: E712
    return {"status": "success", "memories": [_mem(m) for m in rows]}


class MemoryCreate(BaseModel):
    content: str
    category: str = "other"
    importance: int = 4
    follow_up_at: Optional[datetime] = None


@router.post("/{rid}/memories")
async def add_memory(rid: int, body: MemoryCreate, authorization: Optional[str] = Header(None),
                     db: Session = Depends(get_db)):
    _recipient(db, authorization, rid)
    m = P.upsert_memory(db, rid, body.category, body.content, importance=body.importance,
                        follow_up_at=body.follow_up_at, source="caregiver", confidence=1.0)
    return {"status": "success", "memory": _mem(m) if m else None}


@router.delete("/{rid}/memories/{mid}")
async def delete_memory(rid: int, mid: int, authorization: Optional[str] = Header(None),
                        db: Session = Depends(get_db)):
    _recipient(db, authorization, rid)
    m = db.query(RecipientMemory).filter(RecipientMemory.id == mid, RecipientMemory.care_recipient_id == rid).first()
    if not m:
        raise HTTPException(status_code=404, detail="Memory not found")
    m.active = False   # soft delete so it is never re-learned silently from old data
    db.commit()
    return {"status": "success"}


@router.get("/{rid}/context-preview")
async def context_preview(rid: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """Transparency: exactly what Saathi will know in the next conversation."""
    rec = _recipient(db, authorization, rid)
    pctx = P.build_personal_context(db, rid, "", rec.full_name)
    # preview only — do not consume the proactive item
    nxt = P.next_proactive_checkin(db, rid, rec.full_name, force=True)
    return {"status": "success", "address_as": pctx["name"], "prompt_block": P.personal_prompt_block(pctx),
            "next_proactive": nxt, "routine": pctx["routine"], "upcoming_dates": pctx["upcoming_dates"],
            "followup": pctx["followup"], "favourite_media": pctx["favourite_media"]}
