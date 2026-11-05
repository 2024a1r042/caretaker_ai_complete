
from sqlalchemy import create_engine, text
import os
from dotenv import load_dotenv
from datetime import datetime

# Load .env from backend folder
load_dotenv(override=True)

DATABASE_URL = os.getenv("DATABASE_URL")

def migrate():
    if not DATABASE_URL:
        print("DATABASE_URL not found")
        return

    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        print(f"Connected to {DATABASE_URL}")
        
        # 1. Add new columns if they don't exist
        # We use 'IF NOT EXISTS' for column additions isn't standard in all PG versions, 
        # so we'll check information_schema or just wrap in try/except.
        
        cols_to_add = [
            ("title", "TEXT"),
            ("condition_group", "TEXT"),
            ("today_actions", "JSONB"),
            ("resolved_at", "TIMESTAMP"),
            ("archived", "BOOLEAN DEFAULT FALSE")
        ]
        
        for col_name, col_type in cols_to_add:
            try:
                conn.execute(text(f"ALTER TABLE medical_recommendations ADD COLUMN {col_name} {col_type}"))
                print(f"Added column {col_name}")
            except Exception as e:
                print(f"Column {col_name} might already exist: {e}")

        # 2. Archive all existing records that were generated without a specific AI model
        now = datetime.utcnow()
        result = conn.execute(
            text("""
                UPDATE medical_recommendations 
                SET archived = TRUE, resolved_at = :now 
                WHERE model_used IS NULL OR model_used = ''
            """),
            {"now": now}
        )
        conn.commit()
        print(f"Migration complete. {result.rowcount} legacy records archived.")

if __name__ == "__main__":
    migrate()
