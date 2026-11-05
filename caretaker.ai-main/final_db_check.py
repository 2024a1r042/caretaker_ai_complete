import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.getenv('DATABASE_URL'))
Session = sessionmaker(bind=engine)
db = Session()

def check_duplicates(table_name, columns):
    print(f"\n--- Checking {table_name} ---")
    for col in columns:
        result = db.execute(text(f"""
            SELECT {col}, COUNT(*) 
            FROM {table_name} 
            GROUP BY {col} 
            HAVING COUNT(*) > 1
        """)).fetchall()
        if result:
            print(f"[!] DUPLICATE {col.upper()} FOUND:")
            for row in result:
                print(f"  {row[0]} appears {row[1]} times")
        else:
            print(f"  [OK] {col.upper()} is clean.")

try:
    check_duplicates("caretakers", ["username", "email", "phone_number"])
    check_duplicates("care_recipients", ["email", "phone_number"])
except Exception as e:
    print(f"Error during check: {e}")
finally:
    db.close()
