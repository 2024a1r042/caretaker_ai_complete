"""One-time migration: add all missing Medical History columns and tables."""
from config import engine, Base
from sqlalchemy import text, inspect

# Import ALL table models so Base.metadata knows about them
from tables.users import CareTaker, CareRecipient
from tables.medical_reports import MedicalReport
from tables.medical_conditions import PatientCondition, ConditionHistory, LabValue, MedicalAlert

inspector = inspect(engine)
existing_tables = inspector.get_table_names()

with engine.connect() as conn:
    # ── 1. care_recipients: columns added in v3 ──
    print("== care_recipients ==")
    for stmt in [
        "ALTER TABLE care_recipients ADD COLUMN IF NOT EXISTS risk_score FLOAT",
        "ALTER TABLE care_recipients ADD COLUMN IF NOT EXISTS risk_factors_breakdown JSON",
        "ALTER TABLE care_recipients ADD COLUMN IF NOT EXISTS last_analysis_date TIMESTAMP",
        "ALTER TABLE care_recipients ADD COLUMN IF NOT EXISTS last_report_date TIMESTAMP",
    ]:
        conn.execute(text(stmt))
        print(f"  OK: {stmt.split('ADD COLUMN IF NOT EXISTS ')[1]}")

    # ── 2. medical_reports: columns added in v3 ──
    print("\n== medical_reports ==")
    for stmt in [
        "ALTER TABLE medical_reports ADD COLUMN IF NOT EXISTS report_date DATE",
        "ALTER TABLE medical_reports ADD COLUMN IF NOT EXISTS extracted_data JSON",
    ]:
        conn.execute(text(stmt))
        print(f"  OK: {stmt.split('ADD COLUMN IF NOT EXISTS ')[1]}")

    # processing_status is an Enum column – need to create the type first
    conn.execute(text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'reportprocessingstatus') THEN
                CREATE TYPE reportprocessingstatus AS ENUM ('pending','processing','completed','failed');
            END IF;
        END$$;
    """))
    conn.execute(text("""
        ALTER TABLE medical_reports
        ADD COLUMN IF NOT EXISTS processing_status reportprocessingstatus
        DEFAULT 'pending' NOT NULL
    """))
    print("  OK: processing_status ENUM")

    # ── 3. Create brand-new tables if they don't exist ──
    new_tables = ["patient_conditions", "condition_history", "lab_values", "medical_alerts"]
    for tbl in new_tables:
        if tbl not in existing_tables:
            print(f"\n  Creating table: {tbl}")
        else:
            print(f"\n  Table already exists: {tbl}")

    conn.commit()

# Create any tables that don't yet exist (safe – skips existing ones)
Base.metadata.create_all(bind=engine)

print("\n✓ Migration complete!")
