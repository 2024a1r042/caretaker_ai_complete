"""Migration: Add auto_order_enabled and last_auto_order_date columns to medications table."""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import engine
from sqlalchemy import text

def migrate():
    with engine.begin() as conn:
        # Add auto_order_enabled (boolean, default True)
        try:
            conn.execute(text("ALTER TABLE medications ADD COLUMN auto_order_enabled BOOLEAN DEFAULT TRUE"))
            print("  OK: auto_order_enabled added")
        except Exception as e:
            print(f"  Skipped auto_order_enabled: {e}")

        # Add last_auto_order_date (date, nullable)
        try:
            conn.execute(text("ALTER TABLE medications ADD COLUMN last_auto_order_date DATE"))
            print("  OK: last_auto_order_date added")
        except Exception as e:
            print(f"  Skipped last_auto_order_date: {e}")

    print("Migration complete.")

if __name__ == "__main__":
    migrate()
