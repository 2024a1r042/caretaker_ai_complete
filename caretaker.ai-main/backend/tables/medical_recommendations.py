from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
import datetime

from config import Base

# ── Severity ranking used by the dual-model pipeline and dashboard query ─────
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "suggestion": 1}


def severity_rank(s: str) -> int:
    """
    Convert a severity label to an integer weight for comparison.

    Receives: severity string (e.g. "critical", "high", "medium", "suggestion").
    Returns:  int 0-4 (higher = more urgent). Unknown strings map to 0.
    """
    return SEVERITY_RANK.get(str(s).lower(), 0)

class MedicalRecommendation(Base):
    """
    Stores actionable clinical recommendations.

    Records are produced by two sources that write to this single table:
      - The deterministic rule engine (source="rule" | "trend" | "hybrid").
      - The dual-model AI pipeline (source="gemini-flash" | "gemini-pro").

    New columns added for dual-model routing:
      model_used     — which Gemini variant generated this record (nullable for
                       rule-engine records).
      escalated_from — integer FK back to medical_recommendations.id; links a
                       Pro-escalated record to the Flash record that triggered it.
      do_this_now    — single most-important action, plain English, from AI output.
    """
    __tablename__ = "medical_recommendations"

    id = Column(Integer, primary_key=True, index=True)
    care_recipient_id = Column(Integer, ForeignKey("care_recipients.id", ondelete="CASCADE"), nullable=False)
    
    # Recommendation identifiers
    metric = Column(String, nullable=False)  # Example: "HbA1c" or "Combination"
    severity = Column(String, nullable=False) # "critical", "high", "medium", "low", "suggestion"
    message = Column(Text, nullable=False)    # Explanatory text
    
    # Track the exact trigger (for traceability)
    trigger_value = Column(Float, nullable=True)
    reference_range = Column(String, nullable=True)
    
    # Ensure trust
    source = Column(String, default="rule")    # "rule", "trend", "hybrid"
    confidence_score = Column(Float, default=1.0)
    
    # List of grouped actions. Each action dict should have {"type": "doctor_visit", "text": "Consult doctor"}
    actions = Column(JSON, default=list)
    
    # Structured data for automated backend processing (e.g. specific drug names, test types)
    action_payload = Column(JSON, nullable=True)

    # ── Dual-model AI fields (nullable; rule-engine rows leave these blank) ──────

    # Which Gemini model generated this record: "gemini-flash" or "gemini-pro".
    # None means the row was produced by the deterministic rule engine.
    model_used = Column(String, nullable=True)

    # Self-referential FK: when Gemini Pro escalates a Flash recommendation,
    # this points to the originating Flash record's id.
    escalated_from = Column(
        Integer,
        ForeignKey("medical_recommendations.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Plain-English single action for the caregiver (AI output only).
    do_this_now = Column(Text, nullable=True)

    # ── Caregiver-facing AI fields ────────────────────────────────────────────
    # Plain-English message written by the AI for the caregiver dashboard.
    caregiver_message = Column(Text, nullable=True)

    # Emergency escalation flags produced by Gemini Pro.
    call_doctor    = Column(String, nullable=True)   # "true" / "false" string from AI
    call_ambulance = Column(String, nullable=True)   # "true" / "false" string from AI

    # Clinical reasoning written by Gemini Pro for the audit log.
    reasoning = Column(Text, nullable=True)

    # Overall patient health state snapshot at time of generation.
    health_state = Column(String, nullable=True)

    # The action type returned by the AI (e.g. "diet", "lifestyle", "emergency").
    action_type = Column(String, nullable=True)

    # Snapshot of the highest-severity triggered rule that caused this record.
    trigger_context = Column(Text, nullable=True)

    # ── New Enhanced Recommendation Fields ────────────────────────────────────
    
    # "What happens if ignored" — shown below the action card
    why_this_matters = Column(Text, nullable=True)

    # "now | next_hour | today" — drives urgency badge color on dashboard
    time_window = Column(String, nullable=True)

    # Pro only — the identified trigger chain, shown in expandable detail view
    root_cause = Column(Text, nullable=True)

    # Both models — one-line overall state summary
    snapshot_summary = Column(Text, nullable=True)

    # Loop closure instructions
    next_check_when     = Column(String, nullable=True)
    next_check_look_for = Column(Text, nullable=True)
    next_check_if_worse = Column(Text, nullable=True)

    # ── v3 Enhanced Fields ───────────────────────────────────────────────────
    
    # Large, plain-English header (e.g., "Blood sugar management")
    title = Column(String, nullable=True)

    # diabetes | cardiovascular | kidney | liver | vitals | environment | general
    condition_group = Column(String, nullable=True)

    # List of specific actions for today (stored as JSON array)
    today_actions = Column(JSON, nullable=True)

    # State management for dashboard UI
    resolved_at = Column(DateTime, nullable=True)
    archived = Column(Boolean, default=False)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    recipient = relationship("CareRecipient", backref="recommendations")
    escalated_recommendation = relationship(
        "MedicalRecommendation",
        remote_side="MedicalRecommendation.id",
        foreign_keys=[escalated_from],
        uselist=False,
    )
