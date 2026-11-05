from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

target_phone = '7051345437'

with engine.connect() as conn:
    print(f"SEARCHING FOR PHONE: {target_phone}\n")
    
    # 1. Care Recipients
    query1 = text("SELECT id, full_name, email, phone_number FROM care_recipients WHERE phone_number = :phone")
    row1 = conn.execute(query1, {"phone": target_phone}).fetchone()
    if row1:
        print(f"FOUND IN care_recipients: {dict(row1._mapping)}")
    else:
        print("NOT FOUND IN care_recipients")
        
    # 2. Caretakers
    query2 = text("SELECT id, full_name, email, phone_number FROM caretakers WHERE phone_number = :phone")
    row2 = conn.execute(query2, {"phone": target_phone}).fetchone()
    if row2:
        print(f"FOUND IN caretakers: {dict(row2._mapping)}")
    else:
        print("NOT FOUND IN caretakers")
        
    # 3. Doctors (just in case)
    query3 = text("SELECT id, full_name, email, phone_number FROM doctors WHERE phone_number = :phone")
    try:
        row3 = conn.execute(query3, {"phone": target_phone}).fetchone()
        if row3:
            print(f"FOUND IN doctors: {dict(row3._mapping)}")
        else:
            print("NOT FOUND IN doctors")
    except Exception:
        print("TABLE doctors NOT FOUND OR ERROR")
