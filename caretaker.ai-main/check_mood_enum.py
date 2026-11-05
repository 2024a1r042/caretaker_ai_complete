import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv('backend/.env')
DB_URL = os.environ.get('DATABASE_URL')

def check_enum():
    engine = create_engine(DB_URL)
    with engine.connect() as conn:
        res = conn.execute(text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE pg_type.typname = 'moodenum';"))
        labels = [r[0] for r in res]
        print(f"Current labels in moodenum: {labels}")

if __name__ == "__main__":
    check_enum()
