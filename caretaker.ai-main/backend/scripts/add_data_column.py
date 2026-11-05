"""One-off script to add the `data` (bytea) column to the `recordings` table.

Usage:
  .venv\Scripts\activate
  python backend\scripts\add_data_column.py

This script runs a safe `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` so it is idempotent.
"""
import sys
import os
from sqlalchemy import text

# Ensure the backend package path is on sys.path so imports like `from config import engine` work
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from config import engine


def main():
    sql = "ALTER TABLE recordings ADD COLUMN IF NOT EXISTS data bytea;"
    print("Running:", sql)
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
        print("Column added (or already existed).")
    except Exception as e:
        print("Failed to run ALTER TABLE:", e)


if __name__ == '__main__':
    main()
