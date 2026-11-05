from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

with engine.connect() as conn:
    print("--- CARE RECIPIENTS PHONES ---")
    res1 = conn.execute(text("SELECT phone_number, full_name FROM care_recipients"))
    for row in res1:
        print(f"'{row[0]}' - {row[1]}")
        
    print("\n--- CARETAKERS PHONES ---")
    res2 = conn.execute(text("SELECT phone_number, full_name FROM caretakers"))
    for row in res2:
        print(f"'{row[0]}' - {row[1]}")
