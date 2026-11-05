from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import datetime

from config import get_db
from tables.vital_signs import VitalSign
from tables.users import CareRecipient, CareTaker
from repository.users import UsersRepo, JWTRepo


router = APIRouter(tags=["Vitals"])


# ── Pydantic schema for ESP8266 POST body ─────────────────────────────────────
class VitalPayload(BaseModel):
    care_recipient_id: int          # which elder the data belongs to
    secret_key: str                 # simple shared secret to prevent random writes

    # Sensor fields – all optional so ESP can send only what it has
    heart_rate: Optional[int] = None        # bpm  (MAX30102)
    oxygen_saturation: Optional[int] = None # %    (MAX30102)
    temperature: Optional[float] = None     # °C or °F
    systolic_bp: Optional[int] = None       # mmHg (manual / BP module)
    diastolic_bp: Optional[int] = None      # mmHg


# ── Pydantic schema for Manual entry ──────────────────────────────────────────
class ManualVitalPayload(BaseModel):
    care_recipient_id: int
    heart_rate: Optional[int] = None
    oxygen_saturation: Optional[int] = None
    temperature: Optional[float] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    sleep_score: Optional[int] = None
    weight: Optional[float] = None


# Hard-coded key shared with ESP8266 (change this to something private)
ESP_SECRET_KEY = "caretaker_esp_2024"


def _get_username_from_auth(auth_header: Optional[str]):
    if not auth_header:
        return None
    try:
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        token = parts[1]
        decoded = JWTRepo.decode_token(token)
        if not decoded or not isinstance(decoded, dict):
            return None
        return decoded.get('sub')
    except Exception:
        return None


@router.post("/vitals/record")
def record_vitals(payload: VitalPayload, db: Session = Depends(get_db)):
    """
    Called by ESP8266 every N seconds to push live sensor readings.
    Validates the secret key, checks the care_recipient_id exists,
    then inserts a new VitalSign row.
    """

    # 1. Authenticate the device
    if payload.secret_key != ESP_SECRET_KEY:
        raise HTTPException(status_code=403, detail="Invalid device secret key")

    # 2. Verify the care recipient exists
    recipient = db.query(CareRecipient).filter(
        CareRecipient.id == payload.care_recipient_id
    ).first()
    if not recipient:
        raise HTTPException(
            status_code=404,
            detail=f"CareRecipient id={payload.care_recipient_id} not found"
        )

    # 3. Insert new vital sign record
    new_vital = VitalSign(
        care_recipient_id=payload.care_recipient_id,
        heart_rate=payload.heart_rate,
        oxygen_saturation=payload.oxygen_saturation,
        temperature=payload.temperature,
        systolic_bp=payload.systolic_bp,
        diastolic_bp=payload.diastolic_bp,
        recorded_at=datetime.datetime.utcnow()
    )
    db.add(new_vital)
    db.commit()
    db.refresh(new_vital)

    return {
        "status": "ok",
        "recorded_id": new_vital.id,
        "recorded_at": new_vital.recorded_at.isoformat()
    }


@router.post("/vitals/manual")
async def record_vitals_manual(
    payload: ManualVitalPayload, 
    authorization: Optional[str] = Header(None), 
    db: Session = Depends(get_db)
):
    """
    Called by the web dashboard for manual entry.
    Requires JWT authentication.
    """
    username = _get_username_from_auth(authorization)
    if not username:
        raise HTTPException(status_code=401, detail="Unauthorized")

    caretaker = UsersRepo.find_by_username(db, CareTaker, username)
    if not caretaker:
        raise HTTPException(status_code=404, detail="Caretaker not found")

    recipient = db.query(CareRecipient).filter(
        CareRecipient.id == payload.care_recipient_id,
        CareRecipient.caretaker_id == caretaker.id
    ).first()
    
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient not found or access denied")

    # Weight update
    if payload.weight is not None:
        recipient.weight = payload.weight

    # Calculate BMI if possible
    bmi = None
    if recipient.weight and recipient.height:
        # height in cm, weight in kg
        height_m = recipient.height / 100
        bmi = recipient.weight / (height_m * height_m)

    new_vital = VitalSign(
        care_recipient_id=payload.care_recipient_id,
        heart_rate=payload.heart_rate,
        oxygen_saturation=payload.oxygen_saturation,
        temperature=payload.temperature,
        systolic_bp=payload.systolic_bp,
        diastolic_bp=payload.diastolic_bp,
        sleep_score=payload.sleep_score,
        weight=payload.weight,
        bmi=round(bmi, 1) if bmi else None,
        recorded_at=datetime.datetime.utcnow()
    )
    db.add(new_vital)
    db.commit()
    db.refresh(new_vital)

    return {
        "status": "success",
        "message": "Vitals recorded successfully",
        "result": {
            "id": new_vital.id,
            "recorded_at": new_vital.recorded_at.isoformat(),
            "bmi": new_vital.bmi
        }
    }


@router.get("/vitals/latest/{care_recipient_id}")
def get_latest_vitals(care_recipient_id: int, db: Session = Depends(get_db)):
    """Return the most recent vital sign row for a given care recipient."""
    vital = (
        db.query(VitalSign)
        .filter(VitalSign.care_recipient_id == care_recipient_id)
        .order_by(VitalSign.recorded_at.desc())
        .first()
    )
    if not vital:
        raise HTTPException(status_code=404, detail="No vitals found for this recipient")

    return {
        "care_recipient_id": care_recipient_id,
        "heart_rate": vital.heart_rate,
        "oxygen_saturation": vital.oxygen_saturation,
        "temperature": vital.temperature,
        "systolic_bp": vital.systolic_bp,
        "diastolic_bp": vital.diastolic_bp,
        "sleep_score": vital.sleep_score,
        "bmi": vital.bmi,
        "weight": vital.weight,
        "height": vital.height,
        "recorded_at": vital.recorded_at.isoformat() if vital.recorded_at else None
    }
