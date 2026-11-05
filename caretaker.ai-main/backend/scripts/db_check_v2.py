
import sys
import os
from sqlalchemy import text

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SessionLocal

def check():
    db = SessionLocal()
    try:
        # Check recipients
        res = db.execute(text("SELECT id, full_name FROM care_recipients")).fetchall()
        print(f"Recipients: {res}")
        
        # Check audio events
        res = db.execute(text("SELECT care_recipient_id, COUNT(*) FROM audio_events GROUP BY care_recipient_id")).fetchall()
        print(f"Audio Events Stats: {res}")
        
        # Check latest events for 45
        res = db.execute(text("SELECT event_type, confidence, detected_at FROM audio_events WHERE care_recipient_id = 45 ORDER BY detected_at DESC LIMIT 5")).fetchall()
        print(f"Latest events for 45: {res}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check()
