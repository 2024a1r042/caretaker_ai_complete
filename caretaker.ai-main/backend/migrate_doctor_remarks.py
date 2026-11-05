from config import engine
from sqlalchemy import text

with engine.connect() as conn:
    print("== care_recipients ==")
    conn.execute(text("ALTER TABLE care_recipients ADD COLUMN IF NOT EXISTS doctor_remarks TEXT"))
    conn.commit()

print("✓ Migration complete!")
