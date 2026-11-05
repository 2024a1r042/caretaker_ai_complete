"""
MedicationDoseLog Table

One row per scheduled dose slot.  A dose starts as PENDING when the scheduler
fires at the scheduled time.  It moves to TAKEN or MISSED only when a human
(or the system escalation job) explicitly confirms it.

Stock is ONLY decremented when status transitions to TAKEN.
"""

import datetime
import enum
import uuid

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey,
    Integer, String, UniqueConstraint
)
from sqlalchemy.orm import relationship

from config import Base


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class DoseStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    TAKEN   = "TAKEN"
    MISSED  = "MISSED"


class ConfirmationSourceEnum(str, enum.Enum):
    DASHBOARD = "DASHBOARD"
    EMAIL     = "EMAIL"
    VOICE     = "VOICE"
    SYSTEM    = "SYSTEM"   # auto-escalated by the missed-dose scheduler job


# ─────────────────────────────────────────────
# Model
# ─────────────────────────────────────────────

def _new_token() -> str:
    """Generate a fresh UUID4 token string."""
    return str(uuid.uuid4())


class MedicationDoseLog(Base):
    __tablename__ = "medication_dose_logs"

    # ── Primary key ──
    id = Column(Integer, primary_key=True, index=True)

    # ── Foreign keys ──
    medication_id = Column(
        Integer,
        ForeignKey("medications.medication_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    care_recipient_id = Column(
        Integer,
        ForeignKey("care_recipients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Scheduling ──
    scheduled_time = Column(DateTime, nullable=False)

    # ── Lifecycle ──
    status = Column(
        Enum(DoseStatusEnum),
        default=DoseStatusEnum.PENDING,
        nullable=False,
    )
    confirmation_source = Column(Enum(ConfirmationSourceEnum), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)

    # ── Token for email links (UUID4, globally unique) ──
    unique_token = Column(
        String(36),
        default=_new_token,
        unique=True,
        nullable=False,
        index=True,
    )

    # ── Notification tracking ──
    email_sent       = Column(Boolean, default=False, nullable=False, server_default="0")
    escalation_sent  = Column(Boolean, default=False, nullable=False, server_default="0")

    # ── Audit ──
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # ── Relationships ──
    medication = relationship("Medication", back_populates="dose_logs")
    care_recipient = relationship("CareRecipient", back_populates="dose_logs")

    # ── Table-level constraints ──
    __table_args__ = (
        # One PENDING/TAKEN/MISSED log per (medication, scheduled slot).
        # Prevents the scheduler from firing duplicate rows if it ticks twice
        # within the same minute.
        UniqueConstraint(
            "medication_id",
            "scheduled_time",
            name="uq_dose_log_med_slot",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<MedicationDoseLog id={self.id} med={self.medication_id} "
            f"time={self.scheduled_time} status={self.status}>"
        )
