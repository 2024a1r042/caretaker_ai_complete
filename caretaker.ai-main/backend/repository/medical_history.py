"""Repository layer for Medical History system.

CRUD operations for PatientCondition, ConditionHistory, LabValue, MedicalAlert.
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc
from tables.medical_conditions import (
    PatientCondition, ConditionHistory, LabValue, MedicalAlert,
    ConditionStatus
)


# ---------- Patient Conditions ----------

def get_active_conditions(db: Session, recipient_id: int):
    """Get all non-resolved conditions for a recipient."""
    return db.query(PatientCondition).filter(
        PatientCondition.care_recipient_id == recipient_id,
        PatientCondition.status != ConditionStatus.resolved
    ).order_by(desc(PatientCondition.last_updated)).all()


def get_past_conditions(db: Session, recipient_id: int):
    """Get all resolved (past) conditions for a recipient."""
    return db.query(PatientCondition).filter(
        PatientCondition.care_recipient_id == recipient_id,
        PatientCondition.status == ConditionStatus.resolved
    ).order_by(desc(PatientCondition.resolved_date)).all()


def get_all_conditions(db: Session, recipient_id: int):
    """Get all conditions for a recipient."""
    return db.query(PatientCondition).filter(
        PatientCondition.care_recipient_id == recipient_id
    ).order_by(desc(PatientCondition.last_updated)).all()


def get_condition_by_id(db: Session, condition_id: int):
    """Get a single condition by ID."""
    return db.query(PatientCondition).filter(
        PatientCondition.id == condition_id
    ).first()


def create_condition(db: Session, **kwargs):
    """Create a new patient condition."""
    condition = PatientCondition(**kwargs)
    db.add(condition)
    db.flush()
    return condition


# ---------- Condition History ----------

def get_condition_timeline(db: Session, condition_id: int):
    """Get full history timeline for a condition."""
    return db.query(ConditionHistory).filter(
        ConditionHistory.condition_id == condition_id
    ).order_by(ConditionHistory.recorded_at).all()


# ---------- Lab Values ----------

def get_lab_time_series(db: Session, recipient_id: int, metric_name: str = None):
    """Get lab value time-series for a recipient, optionally filtered by metric."""
    query = db.query(LabValue).filter(
        LabValue.care_recipient_id == recipient_id
    )
    if metric_name:
        query = query.filter(LabValue.metric_name == metric_name)
    return query.order_by(LabValue.recorded_date).all()


def get_available_metrics(db: Session, recipient_id: int):
    """Get list of unique metric names available for a recipient."""
    results = db.query(LabValue.metric_name).filter(
        LabValue.care_recipient_id == recipient_id
    ).distinct().all()
    return [r[0] for r in results]


def get_latest_lab_values(db: Session, recipient_id: int):
    """Get the most recent value for each metric."""
    from sqlalchemy import func
    subq = db.query(
        LabValue.metric_name,
        func.max(LabValue.recorded_date).label("max_date")
    ).filter(
        LabValue.care_recipient_id == recipient_id
    ).group_by(LabValue.metric_name).subquery()

    return db.query(LabValue).join(
        subq,
        (LabValue.metric_name == subq.c.metric_name) &
        (LabValue.recorded_date == subq.c.max_date) &
        (LabValue.care_recipient_id == recipient_id)
    ).all()


# ---------- Alerts ----------

def get_unread_alerts(db: Session, recipient_id: int):
    """Get unread alerts for a recipient."""
    return db.query(MedicalAlert).filter(
        MedicalAlert.care_recipient_id == recipient_id,
        MedicalAlert.is_read == False  # noqa E712
    ).order_by(desc(MedicalAlert.created_at)).all()


def get_all_alerts(db: Session, recipient_id: int, limit: int = 50):
    """Get all alerts for a recipient."""
    return db.query(MedicalAlert).filter(
        MedicalAlert.care_recipient_id == recipient_id
    ).order_by(desc(MedicalAlert.created_at)).limit(limit).all()


def mark_alert_read(db: Session, alert_id: int):
    """Mark an alert as read."""
    alert = db.query(MedicalAlert).filter(MedicalAlert.id == alert_id).first()
    if alert:
        alert.is_read = True
        db.flush()
    return alert
