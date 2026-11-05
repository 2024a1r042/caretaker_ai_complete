import os
import sys
sys.path.append(os.path.join(os.getcwd()))

from config import SessionLocal
# Import all tables
from tables.medical_reports import MedicalReport
from tables.video_analysis import VideoAnalysis
from tables.vital_signs import VitalSign
from tables.medical_conditions import PatientCondition, LabValue, MedicalAlert
from tables.conversation_history import ConversationMessage, ProactiveReminder
from tables.environment import EnvironmentSensor
from tables.medications import Medication, MedicationHistory
from tables.allergies import Allergy
from tables.medical_recommendations import MedicalRecommendation
from tables.users import CareRecipient, CareTaker

db = SessionLocal()
try:
    recipient_id = 45
    r = db.query(CareRecipient).filter(CareRecipient.id == recipient_id).first()
    if not r:
        print(f"Recipient ID {recipient_id} not found.")
    else:
        print(f"Recipient: {r.full_name}")
        recs = db.query(MedicalRecommendation).filter(MedicalRecommendation.care_recipient_id == recipient_id).all()
        print(f"Recent Recommendations ({len(recs)}):")
        for rec in recs:
            print(f"- {rec.metric}: {rec.severity} - {rec.message[:50]}...")
            
        labs = db.query(LabValue).filter(LabValue.care_recipient_id == recipient_id).order_by(LabValue.recorded_date.desc()).limit(10).all()
        print(f"\nRecent Labs ({len(labs)}):")
        for l in labs:
            print(f"- {l.metric_name}: {l.metric_value} on {l.recorded_date}")

finally:
    db.close()
