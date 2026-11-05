import asyncio
from config import SessionLocal
from tables.audio_events import AudioEvent, AudioEventType
from tables.users import CareTaker, CareRecipient

def test_db_insert():
    db = SessionLocal()
    try:
        caretaker = db.query(CareTaker).first()
        recipient = db.query(CareRecipient).filter(CareRecipient.caretaker_id == caretaker.id).first()
        
        event = AudioEvent(
            caretaker_id = caretaker.id,
            care_recipient_id = recipient.id,
            event_type = AudioEventType.cough,
            confidence = 88.5,
            duration_ms = 500,
        )
        db.add(event)
        db.commit()
        print("Success! Inserted AudioEvent.")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    test_db_insert()
