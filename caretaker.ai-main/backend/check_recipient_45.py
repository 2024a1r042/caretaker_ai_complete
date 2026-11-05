
import sys
from os import path
sys.path.append(path.dirname(__file__))

# Import all tables to initialize mappers
import tables.users
import tables.medical_conditions
import tables.medical_reports
import tables.allergies
import tables.medications
import tables.vital_signs
import tables.environment

from config import SessionLocal
from tables.users import CareRecipient
import json

def check_recipient(recipient_id):
    db = SessionLocal()
    try:
        recipient = db.query(CareRecipient).filter(CareRecipient.id == recipient_id).first()
        if recipient:
            print(f"Recipient ID: {recipient.id}")
            print(f"Risk Score: {recipient.risk_score}")
            print(f"Risk Factors Breakdown: {recipient.risk_factors_breakdown}")
            print(f"Type of Risk Factors Breakdown: {type(recipient.risk_factors_breakdown)}")
        else:
            print(f"Recipient with ID {recipient_id} not found.")
    except Exception as e:
        print(f"Error during query: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_recipient(45)
