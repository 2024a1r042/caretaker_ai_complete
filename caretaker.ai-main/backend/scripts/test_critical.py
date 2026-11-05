from config import SessionLocal
from services.recommendation_engine import get_state_of_health, generate_recommendations

# Import ALL tables to register them with SQLAlchemy mapper
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

import datetime

db = SessionLocal()
try:
    recipient_id = 51 # Demo Patient
    
    # 1. Clear recs
    from tables.medical_recommendations import MedicalRecommendation
    db.query(MedicalRecommendation).filter(MedicalRecommendation.care_recipient_id == recipient_id).delete()
    
    # 2. Add CRITICAL BP
    db.add(LabValue(
        care_recipient_id=recipient_id,
        metric_name="Systolic BP",
        metric_value=195,
        unit="mmHg",
        is_abnormal=True,
        recorded_date=datetime.datetime.now()
    ))
    db.commit()
    
    # 3. Generate
    generate_recommendations(recipient_id, db)
    
    # 4. Check recs
    recs = db.query(MedicalRecommendation).filter(MedicalRecommendation.care_recipient_id == recipient_id).all()
    print("\n--- CRITICAL TEST ---")
    for r in recs:
        print(f"Metric: {r.metric} | Severity: {r.severity}")
        for a in r.actions:
            print(f"  - Action: {a['text']} (Type: {a['type']})")
            
    # 5. Check Health Status
    status = get_state_of_health(recipient_id, db)
    print(f"\nHealth Status: {status['category']} ({status['label']})")

finally:
    db.close()
