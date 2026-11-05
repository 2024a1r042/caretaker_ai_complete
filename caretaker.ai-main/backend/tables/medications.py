from sqlalchemy import Column, Integer, String, Date, ForeignKey, Enum, Boolean
from sqlalchemy.orm import relationship
from config import Base
import enum

class MedicationStatus(str, enum.Enum):
    active = "active"
    completed = "completed"
    terminated = "terminated"

class Medication(Base):
    __tablename__ = "medications"

    medication_id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(Integer, ForeignKey("care_recipients.id", ondelete="CASCADE"), nullable=False, index=True)
    
    medicine_name = Column(String, nullable=False)
    dosage = Column(String, nullable=True)
    frequency = Column(String, nullable=True)
    schedule_time = Column(String, nullable=True)
    
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    status = Column(Enum(MedicationStatus), default=MedicationStatus.active, nullable=False)
    
    # Stock Management & Auto-Ordering
    current_stock = Column(Integer, default=0, nullable=True)
    doses_per_day = Column(Integer, default=1, nullable=True)
    
    # Tata 1mg Auto-Reorder
    auto_order_enabled = Column(Boolean, default=True, nullable=False, server_default="1")
    last_auto_order_date = Column(Date, nullable=True)

    care_recipient = relationship("CareRecipient", back_populates="active_medications")
    dose_logs = relationship("MedicationDoseLog", back_populates="medication", cascade="all, delete-orphan")

class MedicationHistory(Base):
    __tablename__ = "medication_history"

    history_id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(Integer, ForeignKey("care_recipients.id", ondelete="CASCADE"), nullable=False, index=True)
    
    medicine_name = Column(String, nullable=False)
    dosage = Column(String, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    termination_reason = Column(String, nullable=True)

    care_recipient = relationship("CareRecipient", back_populates="medication_history")
