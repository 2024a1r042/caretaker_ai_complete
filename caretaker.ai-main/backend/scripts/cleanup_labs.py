import sys
import os
sys.path.append(r"e:\model_test\caretaker\backend")

from config import SessionLocal
from sqlalchemy import text

def cleanup_polluted_labs_raw():
    db = SessionLocal()
    try:
        print("Cleaning up polluted lab data via Raw SQL...")
        
        # Define the filters
        polluted_terms = ["mg/dL", "g/dL", "Urea", "Platelets", "RBC", "-", "=", "   "]
        noise_keywords = ["Block", "Sector", "Age", "Reported", "Name", "Gender", "Patient", "Sample", "Collected", "Received", "Dr.", "Laboratory"]
        
        where_clauses = [f"metric_name LIKE '%{term}%'" for term in polluted_terms + noise_keywords]
        where_sql = " OR ".join(where_clauses)
        
        # Execute Delete
        sql = text(f"DELETE FROM lab_values WHERE {where_sql}")
        result = db.execute(sql)
        db.commit()
        
        print(f"SUCCESS: Deleted polluted lab entries. Rows affected: {result.rowcount}")
            
    except Exception as e:
        print(f"ERROR: Raw SQL Cleanup failed: {str(e)}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    cleanup_polluted_labs_raw()
