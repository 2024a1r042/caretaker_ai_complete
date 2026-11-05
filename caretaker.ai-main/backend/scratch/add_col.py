from sqlalchemy import create_engine, text
import os

DB_URL = os.getenv("DATABASE_URL")
engine = create_engine(DB_URL)

def add_column():
    try:
        with engine.connect() as conn:
            # Check if column exists
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='medical_recommendations' and column_name='action_payload';
            """)
            result = conn.execute(check_query).fetchone()
            
            if not result:
                print("Column 'action_payload' missing. Adding it...")
                add_query = text("ALTER TABLE medical_recommendations ADD COLUMN action_payload JSON;")
                conn.execute(add_query)
                conn.commit()
                print("Column added successfully.")
            else:
                print("Column 'action_payload' already exists.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    add_column()
