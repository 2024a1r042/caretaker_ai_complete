from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

with engine.connect() as conn:
    # Check care_recipients
    query = text("SELECT id, full_name, email, phone_number FROM care_recipients WHERE phone_number = '7051345437'")
    row = conn.execute(query).fetchone()
    if row:
        print(f"EXISTING_RECORD: {dict(row._mapping)}")
    else:
        print("NO_RECORD_FOUND")
