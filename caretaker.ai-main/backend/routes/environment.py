from fastapi import APIRouter, HTTPException, Depends, Header, status
from sqlalchemy.orm import Session
from config import get_db
from repository.users import JWTRepo, UsersRepo
from tables.users import CareTaker, CareRecipient
from tables.environment import EnvironmentSensor
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

router = APIRouter()

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

# Pydantic schema for creating a reading
class EnvironmentReadingCreate(BaseModel):
    care_recipient_id: int
    temperature_c: float
    humidity_percent: float
    aqi: Optional[int] = None

class EnvironmentReadingResponse(BaseModel):
    id: int
    care_recipient_id: int
    timestamp: datetime
    temperature_c: float
    humidity_percent: float
    aqi: Optional[int]
    
    class Config:
        from_attributes = True

@router.post("/environment/reading", response_model=EnvironmentReadingResponse)
async def create_environment_reading(
    reading: EnvironmentReadingCreate,
    db: Session = Depends(get_db)
):
    """
    Ingest new sensor data from a room (IoT sensor pushing data).
    No auth required here if IoT devices are pushing from local network, 
    but in production add an API key.
    """
    recipient = db.query(CareRecipient).filter(CareRecipient.id == reading.care_recipient_id).first()
    if not recipient:
        raise HTTPException(status_code=404, detail="Care Recipient not found")
        
    db_reading = EnvironmentSensor(
        care_recipient_id=reading.care_recipient_id,
        temperature_c=reading.temperature_c,
        humidity_percent=reading.humidity_percent,
        aqi=reading.aqi
    )
    
    db.add(db_reading)
    db.commit()
    db.refresh(db_reading)
    
    return db_reading


@router.get("/environment/latest/{recipient_id}", response_model=EnvironmentReadingResponse)
async def get_latest_environment(
    recipient_id: int,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Fetch the most recent environment reading for a specific care recipient.
    """
    # Authenticate
    username = _get_username_from_auth(authorization)
    if not username:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
    user = UsersRepo.find_by_username(db, CareTaker, username)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
    # Verify care recipient belongs to user
    recipient = db.query(CareRecipient).filter(
        CareRecipient.id == recipient_id, 
        CareRecipient.caretaker_id == user.id
    ).first()
    
    if not recipient:
        raise HTTPException(status_code=404, detail="Care Recipient not found or unauthorized")
        
    # Get latest reading
    latest_reading = db.query(EnvironmentSensor).filter(
        EnvironmentSensor.care_recipient_id == recipient_id
    ).order_by(EnvironmentSensor.timestamp.desc()).first()
    
    if not latest_reading:
        raise HTTPException(status_code=404, detail="No environment data found for this recipient")
        
    return latest_reading
