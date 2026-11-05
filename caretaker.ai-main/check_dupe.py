from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("DATABASE_URL not found")
    exit(1)

engine = create_engine(db_url)
with engine.connect() as conn:
    print("Checking care_recipients with phone 7051345437...")
    res = conn.execute(text("SELECT id, full_name, email, username, phone_number FROM care_recipients WHERE phone_number = '7051345437'"))
    recipient = res.fetchone()
    if recipient:
        print(f"Found Care Recipient: {dict(recipient._mapping)}")
    else:
        print("No Care Recipient found with that phone number.")

    print("\nChecking users with phone 7051345437 (if any)...")
    res = conn.execute(text("SELECT id, email, username FROM users WHERE phone_number = '7051345437'"))
    user = res.fetchone()
    if user:
        print(f"Found User: {dict(user._mapping)}")
    else:
        print("No User found with that phone number.")
