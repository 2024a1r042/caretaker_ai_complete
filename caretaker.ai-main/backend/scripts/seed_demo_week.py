import os
import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

import sys
sys.path.append(os.path.join(os.getcwd()))

from config import SessionLocal

# Import all tables to register them with SQLAlchemy mapper
from tables.medical_reports import MedicalReport
from tables.video_analysis import VideoAnalysis
from tables.vital_signs import VitalSign
from tables.medical_conditions import PatientCondition, LabValue, MedicalAlert
from tables.conversation_history import ConversationMessage, ProactiveReminder
from tables.environment import EnvironmentSensor
from tables.medications import Medication, MedicationHistory
from tables.allergies import Allergy
from tables.medical_recommendations import MedicalRecommendation

from tables.users import CareRecipient
from services.recommendation_engine import generate_recommendations

def seed():
    db = SessionLocal()
    from tables.users import CareTaker
    try:
        # 0. Ensure a CareTaker exists for the Demo
        ct = db.query(CareTaker).filter(CareTaker.username == "demo_admin").first()
        if not ct:
            ct = CareTaker(
                username="demo_admin",
                email="demo@example.com",
                phone_number="9876543210",
                password="hashed_password",
                full_name="Demo Admin"
            )
            db.add(ct)
            db.commit()
            db.refresh(ct)
            print(f"Created Demo CareTaker with ID: {ct.id}")

        # 1. Ensure Demo Patient exists
        patient = db.query(CareRecipient).filter(CareRecipient.full_name == "Demo Patient").first()
        if not patient:
            patient = CareRecipient(
                caretaker_id=ct.id,
                full_name="Demo Patient",
                email="demo.patient@example.com",
                phone_number="1234567890",
                age=65,
                gender="Male",
                city="Pune",
                report_summary="Simulated patient for trend detection demo."
            )
            db.add(patient)
            db.commit()
            db.refresh(patient)
            print(f"Created Demo Patient with ID: {patient.id}")
        else:
            print(f"Using Existing Demo Patient ID: {patient.id}")

        # 2. Clear old demo labs to start fresh
        db.execute(text(f"DELETE FROM lab_values WHERE care_recipient_id = {patient.id}"))
        db.execute(text(f"DELETE FROM medical_recommendations WHERE care_recipient_id = {patient.id}"))
        db.commit()

        # 3. Seed 7 days of realistic data with varied trends
        now = datetime.datetime.now(datetime.timezone.utc)
        import random

        # Base trends
        glucose_base = [110, 125, 138, 145, 155, 168, 185] 
        bp_base = [128, 132, 137, 142, 148, 155, 162]
        hb_base = [14.5, 14.3, 14.7, 14.4, 14.6, 14.5, 14.2]
        vitd_base = [12, 15, 18, 22, 26, 30, 32]

        for i in range(7):
            date = now - datetime.timedelta(days=(6-i))
            noise = lambda v: v * (1 + random.uniform(-0.02, 0.02))

            # Fasting Glucose (Worsening)
            g_val = noise(glucose_base[i])
            db.add(LabValue(
                care_recipient_id=patient.id,
                metric_name="Fasting Glucose",
                metric_value=round(g_val, 1),
                normalized_value=float(round(g_val, 1)),
                unit="mg/dL",
                normalized_unit="mg/dL",
                recorded_date=date,
                is_abnormal=(g_val > 100)
            ))

            # Systolic BP (Worsening)
            bp_val = noise(bp_base[i])
            db.add(LabValue(
                care_recipient_id=patient.id,
                metric_name="Systolic BP",
                metric_value=round(bp_val),
                normalized_value=float(round(bp_val)),
                unit="mmHg",
                normalized_unit="mmHg",
                recorded_date=date,
                is_abnormal=(bp_val > 130)
            ))

            # Hemoglobin (Stable)
            hb_val = hb_base[i]
            db.add(LabValue(
                care_recipient_id=patient.id,
                metric_name="Hemoglobin",
                metric_value=round(hb_val, 1),
                normalized_value=float(round(hb_val, 1)),
                unit="g/dL",
                normalized_unit="g/dL",
                recorded_date=date,
                is_abnormal=(hb_val < 13.5)
            ))

            # Vitamin D (Improving)
            vd_val = vitd_base[i]
            db.add(LabValue(
                care_recipient_id=patient.id,
                metric_name="Vitamin D",
                metric_value=round(vd_val, 1),
                normalized_value=float(round(vd_val, 1)),
                unit="ng/mL",
                normalized_unit="ng/mL",
                recorded_date=date,
                is_abnormal=(vd_val < 30)
            ))

            # LDL (High, fluctuating)
            ldl_val = noise(165)
            db.add(LabValue(
                care_recipient_id=patient.id,
                metric_name="LDL",
                metric_value=round(ldl_val, 1),
                normalized_value=float(round(ldl_val, 1)),
                unit="mg/dL",
                normalized_unit="mg/dL",
                recorded_date=date,
                is_abnormal=(ldl_val > 130)
            ))
        
        db.commit()
        print(f"Seeded 35 lab records (7 days x 5 metrics) for {patient.full_name}")

        # 4. Trigger Recommendation Engine
        generate_recommendations(patient.id, db)
        print("Triggered Clinical Recommendation Engine for Demo Patient.")

    except Exception as e:
        db.rollback()
        print(f"Error during seeding: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed()
