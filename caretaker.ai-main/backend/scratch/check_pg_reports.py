
import os
import sys
import psycopg2
from dotenv import load_dotenv

# Add backend to path to import tables if needed, but we'll use raw SQL first
sys.path.append(os.getcwd())

load_dotenv(override=True)
DATABASE_URL = os.getenv("DATABASE_URL")

def check_postgres_reports():
    print(f"Connecting to: {DATABASE_URL}")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Check medical_reports status
        cur.execute("SELECT id, care_recipient_id, processing_status, filename FROM medical_reports;")
        reports = cur.fetchall()
        print(f"\nTotal reports in medical_reports table: {len(reports)}")
        for r in reports:
            print(f"ID: {r[0]}, Recipient: {r[1]}, Status: {r[2]}, File: {r[3]}")
        
        # Check if recipient.report_summary is populated
        cur.execute("SELECT id, full_name, report_summary FROM care_recipients;")
        recipients = cur.fetchall()
        print(f"\nCare Recipients summary status:")
        for rec in recipients:
            summary_len = len(rec[2]) if rec[2] else 0
            print(f"ID: {rec[0]}, Name: {rec[1]}, Summary Length: {summary_len}")
            
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")

if __name__ == "__main__":
    check_postgres_reports()
