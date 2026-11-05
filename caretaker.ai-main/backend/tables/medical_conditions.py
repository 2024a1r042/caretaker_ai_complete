from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date,
    ForeignKey, Enum, Text, JSON
)
from sqlalchemy.orm import relationship
from config import Base
import datetime
import enum


# ---------- Enums ----------

class ConditionStatus(str, enum.Enum):
    active = "active"
    improving = "improving"
    worsening = "worsening"
    controlled = "controlled"
    resolved = "resolved"
    chronic_stable = "chronic_stable"


class ConditionSeverity(str, enum.Enum):
    mild = "mild"
    moderate = "moderate"
    severe = "severe"


class SourceType(str, enum.Enum):
    explicit_diagnosis = "explicit_diagnosis"
    lab_inferred = "lab_inferred"


class AlertType(str, enum.Enum):
    worsening = "worsening"
    improving = "improving"
    resolved = "resolved"
    new_diagnosis = "new_diagnosis"
    critical = "critical"
    monitoring_gap = "monitoring_gap"


class AlertSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class ReportProcessingStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


# ---------- Patient Conditions ----------

class PatientCondition(Base):
    __tablename__ = "patient_conditions"

    id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(
        Integer,
        ForeignKey("care_recipients.id", ondelete="CASCADE"),
        nullable=False, index=True
    )

    # Disease identification (ICD-style)
    disease_code = Column(String, nullable=False, index=True)      # e.g. "E11"
    disease_name = Column(String, nullable=False)                   # e.g. "Type 2 Diabetes Mellitus"

    # Status tracking
    status = Column(Enum(ConditionStatus), default=ConditionStatus.active, nullable=False)
    severity = Column(Enum(ConditionSeverity), nullable=True)
    status_version = Column(Integer, default=1, nullable=False)     # Increments on every status change

    # Timeline
    first_detected = Column(Date, nullable=False)
    last_updated = Column(Date, nullable=False)
    resolved_date = Column(Date, nullable=True)

    # Baseline tracking
    baseline_value = Column(Float, nullable=True)                   # Initial metric value at diagnosis
    baseline_date = Column(Date, nullable=True)                     # When baseline was established

    # Resolution tracking
    consecutive_normal_count = Column(Integer, default=0)           # 3+ → resolved

    # Confidence & source
    confidence_score = Column(Float, default=0.5)                   # 0.0–1.0
    source_type = Column(Enum(SourceType), default=SourceType.lab_inferred)

    # Link to first report that detected this condition
    source_report_id = Column(
        Integer,
        ForeignKey("medical_reports.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    care_recipient = relationship("CareRecipient", back_populates="patient_conditions")
    source_report = relationship("MedicalReport", foreign_keys=[source_report_id])
    history = relationship(
        "ConditionHistory",
        back_populates="condition",
        cascade="all, delete-orphan",
        order_by="ConditionHistory.recorded_at"
    )


# ---------- Condition History (Audit Trail) ----------

class ConditionHistory(Base):
    __tablename__ = "condition_history"

    id = Column(Integer, primary_key=True, index=True)
    condition_id = Column(
        Integer,
        ForeignKey("patient_conditions.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    report_id = Column(
        Integer,
        ForeignKey("medical_reports.id", ondelete="SET NULL"),
        nullable=True
    )

    # State transition
    previous_status = Column(String, nullable=True)
    new_status = Column(String, nullable=False)
    previous_severity = Column(String, nullable=True)
    new_severity = Column(String, nullable=True)
    status_version = Column(Integer, nullable=False)                # Matches condition version at transition

    # Clinical interpretation (doctor-friendly text)
    clinical_interpretation = Column(Text, nullable=True)
    change_reason = Column(Text, nullable=True)

    recorded_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relationships
    condition = relationship("PatientCondition", back_populates="history")
    report = relationship("MedicalReport", foreign_keys=[report_id])


# ---------- Lab Values (Time-Series) ----------

class LabValue(Base):
    __tablename__ = "lab_values"

    id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(
        Integer,
        ForeignKey("care_recipients.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    report_id = Column(
        Integer,
        ForeignKey("medical_reports.id", ondelete="SET NULL"),
        nullable=True
    )

    # Metric data — raw as reported
    metric_name = Column(String, nullable=False, index=True)        # Canonical name (e.g. "HbA1c")
    raw_metric_name = Column(String, nullable=True)                 # Original name as it appeared in report
    metric_value = Column(Float, nullable=False)                    # Raw value
    unit = Column(String, nullable=True)                            # Raw unit as reported

    # Normalized values — all internal logic uses these
    normalized_value = Column(Float, nullable=False)                # Converted to standard unit
    normalized_unit = Column(String, nullable=True)                 # Standard unit (mg/dL, %, mmHg)

    # Reference range
    reference_range_low = Column(Float, nullable=True)
    reference_range_high = Column(Float, nullable=True)
    is_abnormal = Column(Boolean, default=False)
    
    # Mapping status (Industry-level design)
    is_mapped = Column(Boolean, default=True)                       # False if name is unknown
    needs_review = Column(Boolean, default=False)                   # True if value is physiologically weird

    # Change tracking
    pct_change_from_previous = Column(Float, nullable=True)         # % change since last reading
    pct_change_from_baseline = Column(Float, nullable=True)         # % change since baseline

    recorded_date = Column(Date, nullable=False)

    # Traceability (v2 pipeline)
    source_text = Column(Text, nullable=True)                       # Exact line from report that produced this value
    confidence_score = Column(Float, nullable=True, default=0.9)    # 0.0–1.0
    extraction_source = Column(String, nullable=True, default="regex")

    # Relationships
    care_recipient = relationship("CareRecipient", back_populates="lab_values")
    report = relationship("MedicalReport", foreign_keys=[report_id])


# ---------- Lab Parameter Mappings (Learning Layer) ----------

class LabParameterMapping(Base):
    """Stores manual or learned mappings from report-text to canonical metrics."""
    __tablename__ = "lab_parameter_mappings"

    id = Column(Integer, primary_key=True, index=True)
    raw_name = Column(String, unique=True, nullable=False, index=True)  # e.g. "S. Creatinine"
    canonical_name = Column(String, nullable=False, index=True)         # e.g. "Creatinine"
    
    is_approved = Column(Boolean, default=False)                        # True if admin/user confirmed
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ---------- Medical Alerts ----------

class MedicalAlert(Base):
    __tablename__ = "medical_alerts"

    id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(
        Integer,
        ForeignKey("care_recipients.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    condition_id = Column(
        Integer,
        ForeignKey("patient_conditions.id", ondelete="SET NULL"),
        nullable=True
    )

    alert_type = Column(Enum(AlertType), nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(Enum(AlertSeverity), default=AlertSeverity.medium)
    is_read = Column(Boolean, default=False)

    # Throttling
    cooldown_until = Column(DateTime, nullable=True)                # No new alert before this date

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relationships
    care_recipient = relationship("CareRecipient", back_populates="medical_alerts")
    condition = relationship("PatientCondition", foreign_keys=[condition_id])


# ---------- Lab Orders (Doctor Requests) ----------

class LabOrderDetail(Base):
    __tablename__ = "lab_orders"

    id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(
        Integer,
        ForeignKey("care_recipients.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    
    test_name = Column(String, nullable=False)
    order_date = Column(Date, default=datetime.date.today, nullable=False)
    status = Column(String, default="pending")  # pending, completed, cancelled
    doctor_notes = Column(Text, nullable=True)
    
    # Optional link to the result once it arrives
    results_report_id = Column(
        Integer,
        ForeignKey("medical_reports.id", ondelete="SET NULL"),
        nullable=True
    )

    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    # Relationships
    care_recipient = relationship("CareRecipient", back_populates="lab_orders")
