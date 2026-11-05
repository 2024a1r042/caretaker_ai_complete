from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, LargeBinary, Enum, JSON
from sqlalchemy.orm import relationship
from config import Base
import datetime
import enum


class ReportProcessingStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class MedicalReport(Base):
    __tablename__ = 'medical_reports'

    id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(Integer, ForeignKey('care_recipients.id', ondelete='CASCADE'), nullable=False)
    filename = Column(String, nullable=False)
    mime_type = Column(String, nullable=True)
    data = Column(LargeBinary, nullable=True)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)
    analysis_summary = Column(String, nullable=True)                # Cached AI analysis (legacy)

    # Structured extraction fields (v3)
    report_date = Column(Date, nullable=True)                       # Extracted date of the report
    extracted_data = Column(JSON, nullable=True)                    # Raw structured JSON from Gemini
    processing_status = Column(
        Enum(ReportProcessingStatus),
        default=ReportProcessingStatus.pending,
        nullable=False
    )

    # relationship back to recipient
    care_recipient = relationship('CareRecipient', back_populates='medical_reports')
