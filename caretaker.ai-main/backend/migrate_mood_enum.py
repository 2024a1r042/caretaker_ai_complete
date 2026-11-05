import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv('.env')
DB_URL = os.environ.get('DATABASE_URL')

def migrate_enum():
    engine = create_engine(DB_URL)
    new_moods = ['lonely', 'bored', 'relaxed', 'spiritual']
    
    # Connect with AUTOCOMMIT isolation level
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        res = conn.execute(text("SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_enum.enumtypid = pg_type.oid WHERE pg_type.typname = 'moodenum';"))
        existing_labels = {r[0] for r in res}
        
        for mood in new_moods:
            if mood not in existing_labels:
                print(f"Adding {mood} to moodenum...")
                try:
                    conn.execute(text(f"ALTER TYPE moodenum ADD VALUE '{mood}'"))
                    print(f"Successfully added {mood}")
                except Exception as e:
                    print(f"Error adding {mood}: {e}")
            else:
                print(f"{mood} already exists in moodenum.")

if __name__ == "__main__":
    migrate_enum()
