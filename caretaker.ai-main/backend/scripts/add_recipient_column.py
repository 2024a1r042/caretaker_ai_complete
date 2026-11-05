"""One-off script to add the `care_recipient_id` column to the `recordings` table.

Usage:
  .venv\Scripts\activate
  python scripts\add_recipient_column.py

This script runs `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and is idempotent.
"""
import sys
import os
from sqlalchemy import text

# ensure repo root on path
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from config import engine


def main():
    sql = "ALTER TABLE recordings ADD COLUMN IF NOT EXISTS care_recipient_id integer;"
    fk = "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints tc JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name WHERE tc.table_name='recordings' AND tc.constraint_type='FOREIGN KEY' AND kcu.column_name='care_recipient_id') THEN ALTER TABLE recordings ADD CONSTRAINT recordings_care_recipient_fk FOREIGN KEY (care_recipient_id) REFERENCES care_recipients(id) ON DELETE SET NULL; END IF; END$$;"
    print("Running:", sql)
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
            conn.execute(text(fk))
        print("Column and FK added (or already existed).")
    except Exception as e:
        print("Failed to run ALTER TABLE:", e)


if __name__ == '__main__':
    main()
