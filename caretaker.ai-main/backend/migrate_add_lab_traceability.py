"""DB Migration — Add traceability columns to lab_values table.

Run this once to upgrade the existing schema:
    python migrate_add_lab_traceability.py

New columns added to lab_values:
    source_text        TEXT        — The exact line from the report
    confidence_score   FLOAT       — Extraction confidence (0.0–1.0)
    extraction_source  VARCHAR     — 'regex' | 'fuzzy' | 'llm' | 'template'
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import engine
from sqlalchemy import text


MIGRATION_SQL = [
    # Add source_text column
    """
    ALTER TABLE lab_values 
    ADD COLUMN IF NOT EXISTS source_text TEXT DEFAULT NULL;
    """,
    # Add confidence_score column
    """
    ALTER TABLE lab_values 
    ADD COLUMN IF NOT EXISTS confidence_score REAL DEFAULT 0.9;
    """,
    # Add extraction_source column
    """
    ALTER TABLE lab_values 
    ADD COLUMN IF NOT EXISTS extraction_source VARCHAR DEFAULT 'regex';
    """,
]

# SQLite does not support IF NOT EXISTS on ALTER TABLE — handle separately
SQLITE_MIGRATION = """
PRAGMA table_info(lab_values);
"""


def get_existing_columns(conn) -> list[str]:
    """Return list of current column names in lab_values (PostgreSQL + SQLite compatible)."""
    try:
        # PostgreSQL
        result = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'lab_values'"
        ))
        cols = [row[0] for row in result.fetchall()]
        if cols:
            return cols
    except Exception:
        pass
    try:
        # SQLite fallback
        result = conn.execute(text("PRAGMA table_info(lab_values)"))
        return [row[1] for row in result.fetchall()]
    except Exception:
        return []


def run_migration():
    print("=" * 60)
    print("DB MIGRATION: Add traceability columns to lab_values")
    print("=" * 60)

    with engine.connect() as conn:
        existing = get_existing_columns(conn)
        print(f"Existing columns: {existing}")

        added = []

        # source_text
        if "source_text" not in existing:
            conn.execute(text("ALTER TABLE lab_values ADD COLUMN source_text TEXT DEFAULT NULL"))
            added.append("source_text")

        # confidence_score
        if "confidence_score" not in existing:
            conn.execute(text("ALTER TABLE lab_values ADD COLUMN confidence_score FLOAT DEFAULT 0.9"))
            added.append("confidence_score")

        # extraction_source
        if "extraction_source" not in existing:
            conn.execute(text("ALTER TABLE lab_values ADD COLUMN extraction_source VARCHAR(50) DEFAULT 'regex'"))
            added.append("extraction_source")

        conn.commit()

        if added:
            print(f"\n[OK] Migration complete. Added columns: {added}")
        else:
            print("\n[OK] No migration needed -- all columns already exist.")

        final_cols = get_existing_columns(conn)
        print(f"\nFinal columns in lab_values: {final_cols}")
        print("=" * 60)


if __name__ == "__main__":
    run_migration()

