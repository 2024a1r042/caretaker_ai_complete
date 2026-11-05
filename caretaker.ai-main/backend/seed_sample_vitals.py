import sys
import os
import datetime
import random

# Add backend to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import SessionLocal, engine

# Import all models to ensure they are registered in the metadata
import tables.users
import tables.recordings
import tables.medical_reports
import tables.video_analysis
import tables.vital_signs
import tables.audio_events
import tables.medical_conditions
import tables.disease_dictionary
import tables.conversation_history
import tables.environment
import tables.medications
import tables.allergies
import tables.admin

from tables.vital_signs import VitalSign
from tables.users import CareRecipient, GenderEnum

def seed_vitals():
    db = SessionLocal()
    recipient_id = 8
    
    # Check if recipient exists
    recipient = db.query(CareRecipient).filter(CareRecipient.id == recipient_id).first()
    if not recipient:
        print(f"Recipient ID {recipient_id} not found. Creating a dummy recipient.")
        caretaker = db.query(tables.users.CareTaker).first()
        if not caretaker:
            print("No caretaker found to assign recipient. Aborting.")
            return
        
        recipient = CareRecipient(
            id=recipient_id,
            caretaker_id=caretaker.id,
            full_name="Janak Devi",
            email="janak.devi@example.com",
            phone_number="9876543210",
            age=72,
            gender=GenderEnum.female,
            height=170.1,
            weight=85.2,
            blood_group="O+",
            emergency_contact="+91 98765-43210"
        )
        db.add(recipient)
        try:
            db.commit()
            db.refresh(recipient)
        except Exception as e:
            db.rollback()
            print(f"Error creating recipient: {e}")
            return

    print(f"Seeding vitals for {recipient.full_name} (ID: {recipient_id})...")

    # Clear existing vitals for this recipient to ensure the graph looks exactly as requested
    db.query(VitalSign).filter(VitalSign.care_recipient_id == recipient_id).delete()

    # Exact points to mimic Picture 3
    refined_points = [
        ("2026-04-04 21:29:00", 88, 37.2, 5, 96),
        ("2026-04-05 17:54:00", 85, 37.4, 7, 97),
        ("2026-04-06 16:49:00", 91, 37.8, 5, 95),
        ("2026-04-07 16:51:00", 83, 37.5, 7, 97),
        ("2026-04-08 17:29:00", 86, 37.6, 6, 96),
        ("2026-04-09 17:06:00", 89, 37.5, 6, 95),
        ("2026-04-10 20:29:00", 82, 37.7, 8, 98),
        ("2026-04-16 04:07:00", 97, 29.5, 6, 97), # Low temp as shown on graph
    ]

    for dt_str, hr, temp, sleep, spo2 in refined_points:
        recorded_at = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
        v = VitalSign(
            care_recipient_id=recipient_id,
            heart_rate=hr,
            temperature=temp,
            sleep_score=sleep,
            oxygen_saturation=spo2,
            recorded_at=recorded_at,
            systolic_bp=random.randint(110, 130),
            diastolic_bp=random.randint(70, 85),
            weight=recipient.weight,
            bmi=round(recipient.weight / ((recipient.height/100)**2), 1) if recipient.height and recipient.weight else None
        )
        db.add(v)

    db.commit()
    print("Seeding complete.")

if __name__ == "__main__":
    seed_vitals()
