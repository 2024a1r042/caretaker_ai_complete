import os
import sys
import asyncio
from sqlalchemy.orm import Session
import datetime

sys.path.append(os.path.join(os.getcwd()))

from config import SessionLocal
# Need to import tables for relationship resolution
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

from services.insights_engine import run_recommendation_pipeline

async def test_refresh():
    db = SessionLocal()
    try:
        print("Triggering v3 recommendation pipeline for recipient 51...")
        recs = await run_recommendation_pipeline(51, db)
        print(f"Generated {len(recs)} new recommendations.")
        for r in recs:
            print(f"--- NEW REC: {r.id} ---")
            print(f"Title: {r.title}")
            print(f"Group: {r.condition_group}")
            print(f"Do This Now: {r.do_this_now}")
            print(f"Actions: {r.today_actions}")
            print(f"Time Window: {r.time_window}")
            print("-" * 20)
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(test_refresh())
