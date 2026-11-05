"""
SafetyEvent — one row per detected fall / long lie, with the evidence behind
it and what happened next (Saathi's check-in, the person's answer, escalation).
"""

import datetime
import enum

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, JSON, String, Text

from config import Base


class SafetyStatusEnum(str, enum.Enum):
    awaiting_response = "awaiting_response"   # Saathi asked "are you okay?"
    resolved_ok = "resolved_ok"               # person said they're fine
    needs_help = "needs_help"                 # person asked for help / reported pain
    escalated = "escalated"                   # family alerted (help asked, no answer, or long lie)
    acknowledged = "acknowledged"             # caregiver marked it handled
    logged = "logged"                         # historical (uploaded video) — no live check-in


class SafetyEvent(Base):
    __tablename__ = "safety_events"

    id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(Integer, ForeignKey("care_recipients.id", ondelete="CASCADE"), nullable=True, index=True)
    caretaker_id = Column(Integer, ForeignKey("caretakers.id", ondelete="SET NULL"), nullable=True)

    event_type = Column(String, nullable=False)              # fall_confirmed | long_lie
    fall_type = Column(String, nullable=True)                # hard_fall | fall | slow_collapse | out_of_view | found_on_floor
    severity = Column(String, nullable=True)                 # medium | high | critical
    confidence = Column(Float, nullable=True)
    source = Column(String, nullable=True)                   # browser_live | camera_session | upload | simulated
    explanation = Column(Text, nullable=True)
    evidence = Column(JSON, default=list)

    status = Column(Enum(SafetyStatusEnum), default=SafetyStatusEnum.awaiting_response, nullable=False)
    checkin_text = Column(Text, nullable=True)
    response_text = Column(Text, nullable=True)
    escalation_reason = Column(Text, nullable=True)
    time_on_ground_s = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    responded_at = Column(DateTime, nullable=True)
    recovered_at = Column(DateTime, nullable=True)
    escalated_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
