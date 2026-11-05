"""Medical History AI Service — Deterministic risk scoring + Gemini interpretation.

Step 1: Algorithmic, testable, reproducible risk score calculation.
Step 2: Gemini interprets the results (explains, recommends — cannot override score).
"""

import os
import json
import datetime
from sqlalchemy.orm import Session
from utils.gemini_client import call_gemini
from sqlalchemy import desc, func
from dotenv import load_dotenv

load_dotenv()

try:
    import requests
except ImportError:
    requests = None

from tables.medical_conditions import (
    PatientCondition, LabValue, MedicalAlert,
    ConditionStatus, AlertSeverity
)
from tables.users import CareRecipient


# ---------- Risk Score Weights ----------

RISK_WEIGHTS = {
    "chronic_diseases": 0.25,       # Active chronic disease count
    "uncontrolled_conditions": 0.30, # Conditions with worsening/active status
    "critical_labs": 0.20,          # Lab values at critical levels
    "trend_deterioration": 0.15,    # Worsening trends
    "fall_history": 0.10,           # Recent falls
}

MAX_SCORE = 100


# ---------- Deterministic Risk Score Calculator ----------

def calculate_risk_score(recipient_id: int, db: Session) -> dict:
    """Calculate risk score algorithmically. Deterministic, testable, reproducible.

    Returns:
        dict with: risk_score, risk_category, risk_trajectory, factors[]
    """
    factors = []
    component_scores = {}

    # 1. Active chronic diseases (25%)
    active_conditions = db.query(PatientCondition).filter(
        PatientCondition.care_recipient_id == recipient_id,
        PatientCondition.status != ConditionStatus.resolved
    ).all()

    chronic_count = len(active_conditions)
    # Score: 0 conditions = 0, 1 = 30, 2 = 55, 3 = 75, 4+ = 90
    chronic_score = min(chronic_count * 25, 90) if chronic_count else 0
    component_scores["chronic_diseases"] = chronic_score
    if chronic_count > 0:
        names = [c.disease_name for c in active_conditions]
        factors.append({
            "factor": f"{chronic_count} active condition(s): {', '.join(names)}",
            "contribution": round(chronic_score * RISK_WEIGHTS["chronic_diseases"], 1)
        })

    # 2. Uncontrolled conditions (30%)
    uncontrolled = [c for c in active_conditions if c.status in (
        ConditionStatus.worsening, ConditionStatus.active
    )]
    uncontrolled_score = min(len(uncontrolled) * 40, 100)
    component_scores["uncontrolled_conditions"] = uncontrolled_score
    if uncontrolled:
        names = [c.disease_name for c in uncontrolled]
        factors.append({
            "factor": f"{len(uncontrolled)} uncontrolled condition(s): {', '.join(names)}",
            "contribution": round(uncontrolled_score * RISK_WEIGHTS["uncontrolled_conditions"], 1)
        })

    # 3. Critical lab values (20%)
    recent_labs = db.query(LabValue).filter(
        LabValue.care_recipient_id == recipient_id,
        LabValue.is_abnormal == True  # noqa E712
    ).order_by(desc(LabValue.recorded_date)).limit(20).all()

    critical_count = sum(1 for l in recent_labs if _is_critical_lab(l))
    abnormal_count = len(recent_labs) - critical_count
    critical_score = min(critical_count * 50 + abnormal_count * 10, 100)
    component_scores["critical_labs"] = critical_score
    if critical_count > 0:
        factors.append({
            "factor": f"{critical_count} critical lab value(s) detected",
            "contribution": round(critical_score * RISK_WEIGHTS["critical_labs"], 1)
        })
    elif abnormal_count > 0:
        factors.append({
            "factor": f"{abnormal_count} abnormal lab value(s) in recent reports",
            "contribution": round(critical_score * RISK_WEIGHTS["critical_labs"], 1)
        })

    # 4. Trend deterioration (15%)
    worsening_conditions = [c for c in active_conditions if c.status == ConditionStatus.worsening]
    trend_score = min(len(worsening_conditions) * 40, 100)
    component_scores["trend_deterioration"] = trend_score
    if worsening_conditions:
        names = [c.disease_name for c in worsening_conditions]
        factors.append({
            "factor": f"Deteriorating trend in: {', '.join(names)}",
            "contribution": round(trend_score * RISK_WEIGHTS["trend_deterioration"], 1)
        })

    # 5. Fall history (10%) — from video analysis table
    fall_score = _get_fall_risk_score(recipient_id, db)
    component_scores["fall_history"] = fall_score
    if fall_score > 0:
        factors.append({
            "factor": "Recent fall episode(s) detected",
            "contribution": round(fall_score * RISK_WEIGHTS["fall_history"], 1)
        })

    # Calculate weighted total
    risk_score = sum(
        component_scores[k] * RISK_WEIGHTS[k]
        for k in RISK_WEIGHTS
    )
    risk_score = round(min(risk_score, MAX_SCORE), 1)

    # Risk category
    if risk_score >= 75:
        risk_category = "Critical"
    elif risk_score >= 50:
        risk_category = "High"
    elif risk_score >= 25:
        risk_category = "Moderate"
    else:
        risk_category = "Low"

    # Risk trajectory (compare with historical scores)
    trajectory = _calculate_trajectory(recipient_id, risk_score, db)

    result = {
        "risk_score": risk_score,
        "risk_category": risk_category,
        "risk_trajectory": trajectory,
        "factors": factors,
        "component_scores": component_scores,
    }

    # Save to recipient
    recipient = db.query(CareRecipient).filter(
        CareRecipient.id == recipient_id
    ).first()
    if recipient:
        recipient.risk_score = risk_score
        recipient.risk_factors_breakdown = result
        recipient.last_analysis_date = datetime.datetime.utcnow()
        db.flush()

    print(f"[medical_history_ai] Risk score: {risk_score} ({risk_category}), trajectory: {trajectory}")
    return result


# ---------- Gemini AI Interpretation (Step 2) ----------

def analyze_patient_health(recipient_id: int, db: Session) -> dict:
    """Full health analysis: deterministic scoring + Gemini interpretation.

    Step 1: Calculate deterministic risk score
    Step 2: Send structured data to Gemini for interpretation (NOT scoring)
    """
    # Step 1: Deterministic risk
    risk_result = calculate_risk_score(recipient_id, db)

    # Assemble patient state for Gemini
    active_conditions = db.query(PatientCondition).filter(
        PatientCondition.care_recipient_id == recipient_id,
        PatientCondition.status != ConditionStatus.resolved
    ).all()

    past_conditions = db.query(PatientCondition).filter(
        PatientCondition.care_recipient_id == recipient_id,
        PatientCondition.status == ConditionStatus.resolved
    ).all()

    recent_labs = db.query(LabValue).filter(
        LabValue.care_recipient_id == recipient_id
    ).order_by(desc(LabValue.recorded_date)).limit(30).all()

    unread_alerts = db.query(MedicalAlert).filter(
        MedicalAlert.care_recipient_id == recipient_id,
        MedicalAlert.is_read == False  # noqa E712
    ).count()

    patient_state = {
        "risk_score": risk_result["risk_score"],
        "risk_category": risk_result["risk_category"],
        "risk_trajectory": risk_result["risk_trajectory"],
        "contributing_factors": risk_result["factors"],
        "active_conditions": [
            {
                "name": c.disease_name,
                "status": c.status.value if c.status else "unknown",
                "severity": c.severity.value if c.severity else "unknown",
                "since": str(c.first_detected),
                "confidence": c.confidence_score,
                "source": c.source_type.value if c.source_type else "unknown",
            }
            for c in active_conditions
        ],
        "past_conditions": [
            {"name": c.disease_name, "resolved": str(c.resolved_date)}
            for c in past_conditions
        ],
        "recent_labs": [
            {
                "metric": l.metric_name,
                "value": l.normalized_value,
                "unit": l.normalized_unit,
                "date": str(l.recorded_date),
                "abnormal": l.is_abnormal,
            }
            for l in recent_labs[:15]  # Limit for prompt size
        ],
        "unread_alerts": unread_alerts,
    }

    # Step 2: Gemini interprets (does NOT calculate score)
    ai_analysis = _gemini_interpret(patient_state)

    # Merge results
    final = {
        **risk_result,
        "overall_health_status": ai_analysis.get("overall_health_status", "Analysis unavailable"),
        "explanation": ai_analysis.get("explanation", ""),
        "recommendations": ai_analysis.get("recommendations", []),
        "monitoring_frequency": ai_analysis.get("monitoring_frequency", ""),
        "patient_state_summary": patient_state,
    }

    return final


def _gemini_interpret(patient_state: dict) -> dict:
    """Send patient state to Gemini for interpretation only.

    Gemini CANNOT override the risk score — it only explains and recommends.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key or not requests:
        print("[medical_history_ai] Gemini not configured — returning deterministic results only")
        return _fallback_interpretation(patient_state)

    prompt = f"""You are a clinical health analyst for an elderly care monitoring system.
You are given a patient's DETERMINISTIC health state (already calculated by algorithms).

YOUR ROLE:
- Explain the health state in clear, clinical language
- Provide actionable recommendations
- Suggest monitoring frequency
- YOU CANNOT CHANGE THE RISK SCORE — it has been algorithmically calculated

Patient State:
{json.dumps(patient_state, indent=2)}

Return a JSON object with EXACTLY these keys (no markdown, no code fences):
{{
  "overall_health_status": "1-2 sentence overall health summary",
  "explanation": "Detailed explanation of current health state and trends",
  "recommendations": ["Recommendation 1", "Recommendation 2", "Recommendation 3"],
  "monitoring_frequency": "Suggested monitoring frequency (e.g., 'Every 3 months')"
}}
"""

    try:
        data = call_gemini({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": 1500, "temperature": 0.2}
        }, timeout=60, caller="[medical_history_ai]")

        if data and "candidates" in data and data["candidates"]:
            raw = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            if True:
                print(f"[medical_history_ai] Raw Gemini response (first 500 chars): {raw[:500]}")
                # Clean code fences (multiline-safe)
                import re
                cleaned = re.sub(r"```(?:json)?\s*", "", raw, flags=re.DOTALL)
                cleaned = re.sub(r"\s*```", "", cleaned, flags=re.DOTALL).strip()
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    # Fallback: try extracting first { ... } block
                    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
                    if match:
                        try:
                            return json.loads(match.group(0))
                        except json.JSONDecodeError:
                            pass
                    print(f"[medical_history_ai] Failed to parse Gemini response. Cleaned text: {cleaned[:300]}")
                    return _fallback_interpretation(patient_state)

        return _fallback_interpretation(patient_state)

    except Exception as e:
        print(f"[medical_history_ai] Gemini call failed: {e}")
        return _fallback_interpretation(patient_state)


def _fallback_interpretation(patient_state: dict) -> dict:
    """Deterministic fallback when Gemini is unavailable."""
    score = patient_state.get("risk_score", 0)
    category = patient_state.get("risk_category", "Unknown")
    active = patient_state.get("active_conditions", [])
    factors = patient_state.get("contributing_factors", [])

    status_parts = []
    if score >= 50:
        status_parts.append(f"Patient is at {category} risk (score: {score}/100).")
    else:
        status_parts.append(f"Patient is at {category} risk (score: {score}/100).")

    if active:
        names = [c["name"] for c in active]
        status_parts.append(f"Active conditions: {', '.join(names)}.")

    recs = []
    if score >= 50:
        recs.append("Schedule follow-up within 2 weeks")
    if any(c.get("status") == "worsening" for c in active):
        recs.append("Review medication regimen for worsening conditions")
    if factors:
        recs.append("Address contributing risk factors listed in the breakdown")
    if not recs:
        recs.append("Continue routine monitoring")

    return {
        "overall_health_status": " ".join(status_parts),
        "explanation": "; ".join(f["factor"] for f in factors) if factors else "No significant risk factors identified.",
        "recommendations": recs,
        "monitoring_frequency": "Every 3 months" if score >= 50 else "Every 6 months",
    }


# ---------- Helpers ----------

def _is_critical_lab(lab: LabValue) -> bool:
    """Check if a lab value is at critical levels."""
    critical = {
        "Fasting Glucose": (40, 400),
        "Systolic BP": (70, 200),
        "Hemoglobin": (7.0, None),
        "eGFR": (15, None),
        "HbA1c": (None, 12.0),
    }
    if lab.metric_name not in critical:
        return False
    low, high = critical[lab.metric_name]
    if low is not None and lab.normalized_value < low:
        return True
    if high is not None and lab.normalized_value > high:
        return True
    return False


def _get_fall_risk_score(recipient_id: int, db: Session) -> int:
    """Get fall risk score from video analysis data (0-100)."""
    try:
        from tables.video_analysis import VideoAnalysis
        recent_falls = db.query(VideoAnalysis).filter(
            VideoAnalysis.recipient_id == recipient_id,
            VideoAnalysis.fall_detected == True,  # noqa E712
            VideoAnalysis.created_at > datetime.datetime.utcnow() - datetime.timedelta(days=90)
        ).count()
        if recent_falls >= 3:
            return 90
        elif recent_falls == 2:
            return 70
        elif recent_falls == 1:
            return 50
        return 0
    except Exception:
        return 0


def _calculate_trajectory(recipient_id: int, current_score: float, db: Session) -> str:
    """Calculate risk trajectory by comparing with historical scores.

    Returns: 'increasing', 'stable', or 'improving'
    """
    # Get recent risk scores from risk_factors_breakdown history
    recipient = db.query(CareRecipient).filter(
        CareRecipient.id == recipient_id
    ).first()

    if not recipient or not recipient.risk_factors_breakdown:
        return "stable"

    prev_score = recipient.risk_score
    if prev_score is None:
        return "stable"

    diff = current_score - prev_score
    if diff > 5:
        return "increasing"
    elif diff < -5:
        return "improving"
    return "stable"
