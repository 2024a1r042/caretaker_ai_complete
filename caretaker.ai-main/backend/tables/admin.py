from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from config import Base
import datetime


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    is_super_admin = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_id = Column(Integer, ForeignKey("admins.id"), nullable=False)
    admin_username = Column(String, nullable=False)
    action = Column(String, nullable=False)          # e.g. "VERIFY_DOCTOR", "REJECT_DOCTOR", "DELETE_CARETAKER"
    target_type = Column(String, nullable=True)      # e.g. "doctor", "caretaker"
    target_id = Column(Integer, nullable=True)
    target_name = Column(String, nullable=True)
    detail = Column(Text, nullable=True)             # Free-text detail / reason
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
