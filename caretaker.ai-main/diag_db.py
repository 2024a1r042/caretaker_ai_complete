from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

target_phone = '7051345437'
target_username = 'test_user_77'
target_email = 'someone@example.com'

with engine.connect() as conn:
    print(f"DIAGNOSING: {target_username} / {target_email} / {target_phone}\n")
    
    # 1. Caretakers
    print("--- Caretakers ---")
    query_caretakers = text("SELECT id, username, email, phone_number, full_name FROM caretakers")
    rows = conn.execute(query_caretakers).fetchall()
    for row in rows:
        match = ""
        if row.username == target_username: match += "[!] USERNAME MATCH "
        if row.email == target_email: match += "[!] EMAIL MATCH "
        if row.phone_number == target_phone: match += "[!] PHONE MATCH "
        print(f"ID: {row.id} | {row.username} | {row.email} | {row.phone_number} | {row.full_name} {match}")
        
    # 2. Care Recipients
    print("\n--- Care Recipients ---")
    query_recipients = text("SELECT id, full_name, email, phone_number, caretaker_id FROM care_recipients")
    rows = conn.execute(query_recipients).fetchall()
    for row in rows:
        match = ""
        if row.email == target_email: match += "[!] EMAIL MATCH "
        if row.phone_number == target_phone: match += "[!] PHONE MATCH "
        print(f"ID: {row.id} | {row.full_name} | {row.email} | {row.phone_number} | CT_ID: {row.caretaker_id} {match}")
