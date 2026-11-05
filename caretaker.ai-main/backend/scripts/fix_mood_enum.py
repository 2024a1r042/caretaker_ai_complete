from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

# Load database URL from .env
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("[ERROR] DATABASE_URL not found in .env")
    exit(1)

engine = create_engine(DATABASE_URL)

new_moods = ["lonely", "bored", "relaxed", "spiritual"]

with engine.connect() as conn:
    # Check current values in the enum
    try:
        result = conn.execute(text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_type.oid = pg_enum.enumtypid WHERE pg_type.typname = 'moodenum';"))
        existing_moods = [row[0] for row in result]
        print(f"Current moods in DB: {existing_moods}")
        
        for mood in new_moods:
            if mood not in existing_moods:
                print(f"Adding mood: {mood}")
                # ALTER TYPE cannot be run inside a transaction block in some Postgres versions
                # but we'll try it here. SQLAlchemy handles transactions, so we might need isolation_level="AUTOCOMMIT"
                pass
    except Exception as e:
        print(f"Error checking moods: {e}")

# Re-connect with autocommit for ALTER TYPE
engine_autocommit = engine.execution_options(isolation_level="AUTOCOMMIT")
with engine_autocommit.connect() as conn:
    for mood in new_moods:
        try:
            conn.execute(text(f"ALTER TYPE moodenum ADD VALUE '{mood}'"))
            print(f"✅ Successfully added '{mood}' to moodenum.")
        except Exception as e:
            if "already exists" in str(e):
                print(f"ℹ️ '{mood}' already exists.")
            else:
                print(f"❌ Error adding '{mood}': {e}")
