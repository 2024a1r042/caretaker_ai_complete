
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# Assuming the DB is in the same place as config
DB_PATH = r"e:\model_test\caretaker\backend\caretaker.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

import sys
sys.path.append(os.getcwd())

try:
    from tables.medical_reports import MedicalReport
    from tables.users import CareRecipient
    
    reports = db.query(MedicalReport).all()
    print(f"Total reports in DB: {len(reports)}")
    for r in reports:
        print(f"ID: {r.id}, Recipient ID: {r.care_recipient_id}, Status: {r.processing_status}, Filename: {r.filename}")
    
    recipients = db.query(CareRecipient).all()
    print(f"\nTotal recipients in DB: {len(recipients)}")
    for rec in recipients:
        print(f"ID: {rec.id}, Name: {rec.full_name}, Summary length: {len(rec.report_summary) if rec.report_summary else 0}")

finally:
    db.close()
