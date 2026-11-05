import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from config import SessionLocal
db = SessionLocal()
try:
    from sqlalchemy import text
    result = db.execute(text("SELECT id, filename, processing_status, report_date FROM medical_reports WHERE care_recipient_id = 45"))
    rows = result.fetchall()
    with open("lab_check_output.md", "w") as f:
        f.write("# Lab Check Output\n\n## Reports\n\n")
        for r in rows:
            f.write(f"- ID:{r[0]} | {r[1]} | status:{r[2]} | date:{r[3]}\n")
        result2 = db.execute(text("SELECT id, metric_name, normalized_value, normalized_unit, recorded_date, report_id, is_abnormal FROM lab_values WHERE care_recipient_id = 45 ORDER BY recorded_date"))
        labs = result2.fetchall()
        f.write(f"\n## Lab Values ({len(labs)} rows)\n\n")
        for l in labs:
            f.write(f"- ID:{l[0]} | {l[1]} = {l[2]} {l[3]} | date:{l[4]} | report_id:{l[5]} | abnormal:{l[6]}\n")
    print("Done")
except Exception as e:
    print(f"Error: {e}")
    import traceback; traceback.print_exc()
finally:
    db.close()
