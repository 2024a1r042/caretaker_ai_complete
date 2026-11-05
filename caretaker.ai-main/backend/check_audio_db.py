import sys
import os
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from tables.users import CareTaker, CareRecipient
from tables.video_analysis import VideoAnalysis
from tables.medical_reports import MedicalReport
from tables.vital_signs import VitalSign
sys.path.append(os.getcwd())

from tables.audio_events import AudioEvent
from config import DATABASE_URL

def check_db():
    print("--- Checking Audio Events in DB ---")
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        db = SessionLocal()
        
        # Get last 5 events
        stmt = select(AudioEvent).order_by(AudioEvent.detected_at.desc()).limit(5)
        events = db.execute(stmt).scalars().all()
        
        if not events:
            print("No audio events found in database.")
        else:
            print(f"Found {len(events)} recent events:")
            for event in events:
                print(f"[{event.detected_at}] Type: {event.event_type}, Confidence: {event.confidence:.2f}%")
                
        db.close()
        print("--- DB Check Complete ---")
        
    except Exception as e:
        print(f"[FAIL] Database check failed: {e}")

if __name__ == "__main__":
    check_db()
