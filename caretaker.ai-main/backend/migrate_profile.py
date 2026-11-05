import os
from sqlalchemy import text
from config import engine

def alter_tables():
    with engine.connect() as conn:
        columns_to_add = [
            ("care_recipients", "height", "FLOAT"),
            ("care_recipients", "weight", "FLOAT"),
            ("care_recipients", "blood_group", "VARCHAR"),
            ("care_recipients", "emergency_contact", "VARCHAR"),
            ("care_recipients", "registration_date", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]

        for table, col, col_type in columns_to_add:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}"))
                conn.commit()
                print(f"Successfully added {col} to {table}")
            except Exception as e:
                # In PostgreSQL, DuplicateColumn is raised for "column already exists"
                if "already exists" in str(e):
                    print(f"Column {col} already exists in {table}")
                else:
                    print(f"Error adding {col} to {table}: {e}")
                    
if __name__ == "__main__":
    alter_tables()
