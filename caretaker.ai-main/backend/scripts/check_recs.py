import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

import sys
sys.path.append(os.path.join(os.getcwd()))

from config import SessionLocal
from tables.users import CareRecipient, CareTaker
from tables.medical_reports import MedicalReport
from tables.video_analysis import VideoAnalysis
from tables.vital_signs import VitalSign
from tables.medical_conditions import PatientCondition, LabValue, MedicalAlert
from tables.conversation_history import ConversationMessage, ProactiveReminder
from tables.environment import EnvironmentSensor
from tables.medications import Medication, MedicationHistory
from tables.allergies import Allergy
from tables.medical_recommendations import MedicalRecommendation

def check():
    db = SessionLocal()
    try:
        recs = db.query(MedicalRecommendation).filter(MedicalRecommendation.care_recipient_id == 51).all()
        for r in recs:
            print(f"Metric: {r.metric} | Severity: {r.severity} | Message: {r.message}")
            for a in r.actions:
                print(f"  - Action [{a['type']}]: {a['text']}")
    finally:
        db.close()

if __name__ == "__main__":
    check()
