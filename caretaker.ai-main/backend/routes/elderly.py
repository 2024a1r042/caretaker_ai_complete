from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.orm import Session
from typing import Optional, Dict
import json
from datetime import datetime

from config import get_db
from tables.users import CareTaker
from repository.users import UsersRepo, JWTRepo

router = APIRouter(prefix="/api/elderly", tags=["elderly"])

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

# Simple storage for face profiles
registered_faces = {}

@router.post("/register-face")
async def register_face(
    name: str,
    face_descriptor: str,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Register a face for monitoring
    """
    try:
        username = _get_username_from_auth(authorization)
        if not username:
            raise HTTPException(status_code=401, detail="Missing or invalid token")

        user = UsersRepo.find_by_username(db, CareTaker, username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Parse face descriptor
        face_data = json.loads(face_descriptor)
        
        elder_id = f"elder_{user.id}_{len(registered_faces) + 1}"
        registered_faces[elder_id] = {
            "name": name,
            "face_descriptor": face_data,
            "caretaker_id": user.id,
            "registered_at": datetime.now().isoformat()
        }

        return {
            "status": "success",
            "elder_id": elder_id,
            "message": "Face registered for monitoring"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register face: {str(e)}")

@router.get("/profiles")
async def get_face_profiles(authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    """
    Get registered face profiles
    """
    try:
        username = _get_username_from_auth(authorization)
        if not username:
            raise HTTPException(status_code=401, detail="Missing or invalid token")

        user = UsersRepo.find_by_username(db, CareTaker, username)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Return faces for this user
        user_faces = {
            k: v for k, v in registered_faces.items() 
            if v.get("caretaker_id") == user.id
        }

        return {
            "status": "success",
            "profiles": user_faces
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get profiles: {str(e)}")