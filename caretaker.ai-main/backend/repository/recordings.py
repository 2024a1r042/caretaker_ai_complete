from sqlalchemy.orm import Session
from tables.recordings import Recording
import os
import datetime

class RecordingsRepo:
    @staticmethod
    def create(db: Session, caretaker_id: int, filename: str, path: str = None, data: bytes = None, mime_type: str = 'audio/wav', duration: float = None, care_recipient_id: int = None):
        rec = Recording(
            caretaker_id=caretaker_id,
            care_recipient_id=care_recipient_id,
            filename=filename,
            path=path or '',
            data=data,
            mime_type=mime_type,
            duration=duration
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec

    @staticmethod
    def list_for_caretaker(db: Session, caretaker_id: int):
        return db.query(Recording).filter(Recording.caretaker_id == caretaker_id).order_by(Recording.created_at.desc()).all()
