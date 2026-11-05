from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Header, Form
from sqlalchemy.orm import Session
import os
from typing import Optional

from config import get_db
from repository.recordings import RecordingsRepo
from repository.users import UsersRepo, JWTRepo
from tables.users import CareTaker
from tables.recordings import Recording
from fastapi.responses import Response, FileResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recordings", tags=["Recordings"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), '..', 'uploads')
UPLOAD_DIR = os.path.abspath(UPLOAD_DIR)
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _get_username_from_auth(auth_header: Optional[str]):
    if not auth_header:
        logger.warning("No Authorization header provided")
        return None
    
    try:
        # expected: "Bearer <token>"
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning(f"Invalid Authorization header format: {auth_header[:50]}...")
            return None
            
        token = parts[1]
        if not token:
            logger.warning("Empty token")
            return None
            
        logger.debug(f"Attempting to decode token: {token[:10]}...")
        decoded = JWTRepo.decode_token(token)
        
        if not decoded or not isinstance(decoded, dict) or 'sub' not in decoded:
            logger.warning("Invalid token content")
            return None
            
        logger.debug(f"Successfully decoded token for user: {decoded['sub']}")
        return decoded['sub']
        
    except Exception as e:
        logger.error(f"Error decoding token: {str(e)}")
        return None


@router.post('/upload')
async def upload_recording(file: UploadFile = File(...), authorization: Optional[str] = Header(None), db: Session = Depends(get_db), care_recipient_id: Optional[int] = Form(None)):
    try:
        username = _get_username_from_auth(authorization)
        if not username:
            logger.warning("Authentication failed: Missing or invalid token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"status": "error", "message": "Authentication required"}
            )

        user = UsersRepo.find_by_username(db, CareTaker, username)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Read file bytes and store them in DB (no mandatory disk write)
        filename = file.filename
        safe_name = filename.replace('..', '').replace('/', '_')
        content = await file.read()

        # Try to store bytes in DB; if DB schema doesn't support it, fall back to saving on disk
        try:
            rec = RecordingsRepo.create(db, caretaker_id=user.id, filename=safe_name, path='', data=content, mime_type=file.content_type or 'audio/wav', care_recipient_id=care_recipient_id)
            return {"status": "success", "recording": {"id": rec.id, "filename": rec.filename, "created_at": rec.created_at.isoformat()}}
        except Exception as e:
            logger.exception("DB storage failed, attempting disk fallback")
            # rollback and fallback to disk storage
            try:
                db.rollback()
            except Exception:
                pass
            try:
                user_dir = os.path.join(UPLOAD_DIR, username)
                os.makedirs(user_dir, exist_ok=True)
                dest_path = os.path.join(user_dir, safe_name)
                with open(dest_path, 'wb') as f:
                    f.write(content)
                rec = RecordingsRepo.create(db, caretaker_id=user.id, filename=safe_name, path=dest_path, data=None, mime_type=file.content_type or 'audio/wav', care_recipient_id=care_recipient_id)
                return {"status": "success", "recording": {"id": rec.id, "filename": rec.filename, "created_at": rec.created_at.isoformat(), "note": "stored-on-disk-fallback"}}
            except Exception as e2:
                logger.exception("Disk fallback failed")
                # final failure
                try:
                    db.rollback()
                except Exception:
                    pass
                raise HTTPException(status_code=500, detail=f"Failed storing recording: {str(e)} | fallback: {str(e2)}")
    except HTTPException:
        # re-raise HTTP exceptions as-is
        raise
    except Exception as err:
        logger.exception("Unexpected error in upload_recording")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(err)}")


@router.get('/my')
async def list_my_recordings(authorization: Optional[str] = Header(None), db: Session = Depends(get_db), care_recipient_id: Optional[int] = None):
    try:
        username = _get_username_from_auth(authorization)
        if not username:
            logger.warning("Authentication failed: Missing or invalid token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"status": "error", "message": "Authentication required"}
            )

        user = UsersRepo.find_by_username(db, CareTaker, username)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if care_recipient_id:
            recs = db.query(Recording).filter(Recording.caretaker_id == user.id, Recording.care_recipient_id == care_recipient_id).order_by(Recording.created_at.desc()).all()
        else:
            recs = RecordingsRepo.list_for_caretaker(db, user.id)
        return {"status": "success", "recordings": [{"id": r.id, "filename": r.filename, "created_at": r.created_at.isoformat()} for r in recs]}
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("Unexpected error listing recordings")
        raise HTTPException(status_code=500, detail=f"Failed to list recordings: {str(err)}")


@router.get("/{rec_id}/download")
async def download_recording(rec_id: int, authorization: Optional[str] = Header(None), db: Session = Depends(get_db)):
    try:
        username = _get_username_from_auth(authorization)
        if not username:
            logger.warning("Authentication failed: Missing or invalid token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"status": "error", "message": "Authentication required"}
            )

        user = UsersRepo.find_by_username(db, CareTaker, username)
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        rec = db.query(Recording).filter(Recording.id == rec_id, Recording.caretaker_id == user.id).first()
        if not rec:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

        # Prefer DB-stored bytes
        if rec.data:
            return Response(content=rec.data, media_type=rec.mime_type or 'application/octet-stream', headers={"Content-Disposition": f"attachment; filename=\"{rec.filename}\""})

        # Fallback to file path if present
        if rec.path and os.path.exists(rec.path):
            return FileResponse(rec.path, media_type=rec.mime_type or 'application/octet-stream', filename=rec.filename)

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording data not available")
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("Unexpected error downloading recording")
        raise HTTPException(status_code=500, detail=f"Failed to download recording: {str(err)}")
