"""
Migration: Add admin tables and doctor verification columns.
Run with: python migrate_admin.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from config import engine, SessionLocal, Base
from sqlalchemy import inspect, text
from tables.admin import Admin, AuditLog


def run():
    inspector = inspect(engine)

    # 1. Create admin and audit_log tables if they don't exist
    Base.metadata.create_all(bind=engine, tables=[Admin.__table__, AuditLog.__table__])
    print("[OK] Admin tables created (or already exist).")

    # 2. Add doctor verification columns (safe ALTER TABLE, no-ops if columns exist)
    if inspector.has_table("doctors"):
        existing_cols = [c["name"] for c in inspector.get_columns("doctors")]

        with engine.begin() as conn:
            if "is_verified" not in existing_cols:
                conn.execute(text("ALTER TABLE doctors ADD COLUMN is_verified BOOLEAN DEFAULT FALSE"))
                print("[OK] Added is_verified to doctors.")
            if "verified_at" not in existing_cols:
                conn.execute(text("ALTER TABLE doctors ADD COLUMN verified_at TIMESTAMP"))
                print("[OK] Added verified_at to doctors.")
            if "verified_by_admin_id" not in existing_cols:
                conn.execute(text("ALTER TABLE doctors ADD COLUMN verified_by_admin_id INTEGER"))
                print("[OK] Added verified_by_admin_id to doctors.")
            if "rejection_reason" not in existing_cols:
                conn.execute(text("ALTER TABLE doctors ADD COLUMN rejection_reason TEXT"))
                print("[OK] Added rejection_reason to doctors.")
    else:
        print("[WARN] doctors table not found -- skipping column migration.")

    # 3. Seed default admin if not already present
    db = SessionLocal()
    try:
        # Load from env or use defaults
        admin_user = os.getenv("ADMIN_USERNAME", "admin")
        admin_pass = os.getenv("ADMIN_PASSWORD", "caretaker")
        
        existing_admin = db.query(Admin).filter(Admin.username == admin_user).first()
        if not existing_admin:
            admin = Admin(
                username=admin_user,
                email="admin@caretaker.ai",
                password=admin_pass,
                full_name="Platform Admin",
                is_super_admin=True
            )
            db.add(admin)
            db.commit()
            print(f"[OK] Default admin created: username={admin_user}  password={'*' * len(admin_pass)}")
        else:
            # Synchronize password if it differs from ENV
            if existing_admin.password != admin_pass:
                existing_admin.password = admin_pass
                db.commit()
                print(f"[OK] Admin '{admin_user}' password updated to match .env configuration.")
            else:
                print(f"[INFO] Admin '{admin_user}' already exists and matches .env -- skipping seed.")
    finally:
        db.close()

    print("\n[DONE] Migration complete.")


if __name__ == "__main__":
    run()
