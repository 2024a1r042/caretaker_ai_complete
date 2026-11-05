from config import engine
from sqlalchemy import text

with engine.connect() as conn:
    print("== medications ==")
    for stmt in [
        "ALTER TABLE medications ADD COLUMN IF NOT EXISTS current_stock INTEGER DEFAULT 0",
        "ALTER TABLE medications ADD COLUMN IF NOT EXISTS doses_per_day INTEGER DEFAULT 1",
        "ALTER TABLE medications ADD COLUMN IF NOT EXISTS auto_order_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE medications ADD COLUMN IF NOT EXISTS last_auto_order_date DATE",
    ]:
        conn.execute(text(stmt))
        print(f"  OK: {stmt.split('ADD COLUMN IF NOT EXISTS ')[1]}")
    conn.commit()

print("✓ Migration complete!")
