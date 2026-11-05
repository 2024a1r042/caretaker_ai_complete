import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

sys.path.append(os.path.join(os.getcwd()))

from config import SessionLocal
from tables.medical_recommendations import MedicalRecommendation
from tables.users import CareRecipient, CareTaker
from tables.video_analysis import VideoAnalysis
from tables.medical_conditions import PatientCondition, LabValue
from tables.vital_signs import VitalSign
from tables.medications import Medication
from tables.medication_dose_logs import MedicationDoseLog
from tables.allergies import Allergy
from tables.conversation_history import ConversationMessage
from tables.medical_reports import MedicalReport
from tables.audio_events import AudioEvent
from tables.environment import EnvironmentSensor

def check():
    db = SessionLocal()
    try:
        recs = db.query(MedicalRecommendation).filter(MedicalRecommendation.care_recipient_id == 51).all()
        print(f"Found {len(recs)} recommendations for recipient 51")
        for r in recs:
            print(f"--- ID: {r.id} ---")
            print(f"Title: {r.title}")
            print(f"Condition: {r.condition_group}")
            print(f"Metric: {r.metric} | Severity: {r.severity}")
            print(f"Message: {r.message}")
            print(f"Do This Now: {r.do_this_now}")
            print(f"Today Actions: {r.today_actions}")
            print(f"Resolved At: {r.resolved_at}")
            print(f"Archived: {r.archived}")
            print("-" * 20)
    finally:
        db.close()

if __name__ == "__main__":
    check()
