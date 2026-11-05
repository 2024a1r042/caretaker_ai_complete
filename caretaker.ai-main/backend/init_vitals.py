
import sys
import os
import random
from datetime import datetime, timedelta

# Add backend to path so we can import config/tables
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from sqlalchemy.orm import Session
from datetime import datetime
from config import engine, Base, SessionLocal
from tables.users import CareRecipient
from tables.vital_signs import VitalSign
import tables.video_analysis  # Register VideoAnalysis
import tables.medical_reports # Register MedicalReport

def init_vitals():
    print("Initializing Vital Signs table...")
    
    # Create tables if they don't exist
    # This will create vital_signs table because it's imported via tables.vital_signs
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # Get all care recipients
        recipients = db.query(CareRecipient).all()
        if not recipients:
            print("No Care Recipients found! Please register a recipient first.")
            return

        print(f"Found {len(recipients)} recipients. Adding sample data...")

        for r in recipients:
            # Check if vitals already exist for this recipient (optional, but good to avoid dupes on re-run)
            existing = db.query(VitalSign).filter(VitalSign.care_recipient_id == r.id).first()
            if existing:
                print(f"Skipping {r.full_name} (already has data)")
                continue

            # Generate random vitals
            hr = random.randint(60, 90)
            sys_bp = random.randint(110, 140)
            dia_bp = random.randint(70, 90)
            spo2 = random.randint(95, 100)
            temp = round(random.uniform(97.0, 99.5), 1)
            sleep = random.randint(50, 90)
            
            # Height/Weight for BMI (metric for calculation)
            # stored as float
            height_m = random.uniform(1.6, 1.85)
            weight_kg = random.uniform(60, 90)
            bmi = round(weight_kg / (height_m * height_m), 1)

            vital = VitalSign(
                care_recipient_id=r.id,
                heart_rate=hr,
                systolic_bp=sys_bp,
                diastolic_bp=dia_bp,
                oxygen_saturation=spo2,
                sleep_score=sleep,
                temperature=temp,
                bmi=bmi,
                height=round(height_m * 100, 1), # cm
                weight=round(weight_kg, 1),      # kg
                recorded_at=datetime.utcnow() - timedelta(minutes=random.randint(1, 60))
            )
            db.add(vital)
            print(f"Added vitals for {r.full_name}: HR={hr}, BP={sys_bp}/{dia_bp}")

        db.commit()
        print("Done!")

    except Exception as e:
        import traceback
        with open("error.log", "w") as f:
            f.write(traceback.format_exc())
            f.write(f"\nError: {e}")
        print(f"Error logged to error.log")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_vitals()
