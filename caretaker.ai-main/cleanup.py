from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv

load_dotenv()
db_url = os.getenv("DATABASE_URL")
engine = create_engine(db_url)

with engine.connect() as conn:
    print("Deleting caretaker with ID 2...")
    conn.execute(text("DELETE FROM caretakers WHERE id = 2"))
    conn.commit()
    print("DONE.")
