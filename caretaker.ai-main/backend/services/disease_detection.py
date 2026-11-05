"""Disease Detection Engine — Detects diseases from report data.

Combines explicit diagnoses from reports with lab-value-inferred diseases.
Sets confidence scores and source types. Handles deduplication.
"""

import datetime
from sqlalchemy.orm import Session
from tables.medical_conditions import (
    PatientCondition, ConditionHistory, ConditionStatus,
    ConditionSeverity, SourceType
)
from tables.disease_dictionary import DiseaseDictionary


# ---------- Unit Normalization ----------

# Standard units for each metric — all internal logic uses these
STANDARD_UNITS = {
    "HbA1c": "%",
    "Fasting Glucose": "mg/dL",
    "Post-Prandial Glucose": "mg/dL",
    "Systolic BP": "mmHg",
    "Diastolic BP": "mmHg",
    "Total Cholesterol": "mg/dL",
    "LDL": "mg/dL",
    "HDL": "mg/dL",
    "Triglycerides": "mg/dL",
    "Creatinine": "mg/dL",
    "eGFR": "mL/min",
    "Hemoglobin": "g/dL",
    "Hematocrit": "%",
    "Ferritin": "ng/mL",
    "TSH": "mIU/L",
    "T3": "pg/mL",
    "T4": "µg/dL",
    "Uric Acid": "mg/dL",
    "BUN": "mg/dL",
}

# Conversion factors: {metric: {source_unit: (multiplier, target_unit)}}
UNIT_CONVERSIONS = {
    "Fasting Glucose": {"mmol/L": (18.018, "mg/dL"), "mmol/l": (18.018, "mg/dL")},
    "Post-Prandial Glucose": {"mmol/L": (18.018, "mg/dL"), "mmol/l": (18.018, "mg/dL")},
    "Total Cholesterol": {"mmol/L": (38.67, "mg/dL"), "mmol/l": (38.67, "mg/dL")},
    "LDL": {"mmol/L": (38.67, "mg/dL"), "mmol/l": (38.67, "mg/dL")},
    "HDL": {"mmol/L": (38.67, "mg/dL"), "mmol/l": (38.67, "mg/dL")},
    "Triglycerides": {"mmol/L": (88.57, "mg/dL"), "mmol/l": (88.57, "mg/dL")},
    "Creatinine": {
        "µmol/L": (0.0113, "mg/dL"), "umol/L": (0.0113, "mg/dL"),
        "µmol/l": (0.0113, "mg/dL"), "umol/l": (0.0113, "mg/dL"),
    },
}


def normalize_lab_value(value: float, unit: str, metric_name: str) -> tuple:
    """Normalize a lab value to standard units.

    Returns:
        (normalized_value, normalized_unit)
    """
    if not unit:
        return value, STANDARD_UNITS.get(metric_name, "")

    standard = STANDARD_UNITS.get(metric_name, "")
    if unit == standard:
        return value, standard

    conversions = UNIT_CONVERSIONS.get(metric_name, {})
    if unit in conversions:
        multiplier, target = conversions[unit]
        return round(value * multiplier, 2), target

    # No conversion found — return as-is
    return value, unit or standard


# ---------- Disease Name Mapping ----------

# Map common disease names from Gemini output to ICD codes
DISEASE_NAME_TO_CODE = {
    "type 2 diabetes": "E11",
    "type 2 diabetes mellitus": "E11",
    "diabetes mellitus": "E11",
    "diabetes": "E11",
    "t2dm": "E11",
    "hypertension": "I10",
    "high blood pressure": "I10",
    "htn": "I10",
    "hyperlipidemia": "E78",
    "dyslipidemia": "E78",
    "high cholesterol": "E78",
    "hypercholesterolemia": "E78",
    "anemia": "D64",
    "iron deficiency anemia": "D64",
    "chronic kidney disease": "N18",
    "ckd": "N18",
    "renal failure": "N18",
    "hypothyroidism": "E03",
    "underactive thyroid": "E03",
    "hyperthyroidism": "E05",
    "overactive thyroid": "E05",
    "hyperuricemia": "E87",
    "gout": "E87",
}


def _match_disease_code(disease_name: str) -> tuple:
    """Match a disease name to its ICD code and canonical name.

    Returns:
        (code, canonical_name) or (None, None) if not matched
    """
    lower = disease_name.strip().lower()
    code = DISEASE_NAME_TO_CODE.get(lower)
    if code:
        # Get canonical name from our mapping
        canonical_names = {
            "E11": "Type 2 Diabetes Mellitus",
            "I10": "Hypertension",
            "E78": "Hyperlipidemia",
            "D64": "Anemia",
            "N18": "Chronic Kidney Disease",
            "E03": "Hypothyroidism",
            "E05": "Hyperthyroidism",
            "E87": "Hyperuricemia",
        }
        return code, canonical_names.get(code, disease_name)
    return None, None


# ---------- Lab-Value Based Detection ----------

def detect_diseases_from_lab_values(lab_values: dict) -> list:
    """Detect diseases from lab values using threshold rules.

    Args:
        lab_values: Dict of {metric_name: {"value": float, "unit": str}}

    Returns:
        List of detected disease dicts with: disease_code, disease_name, confidence_score,
        source_type, triggering_metric, triggering_value
    """
    detected = []

    for metric_name, val_info in lab_values.items():
        if not isinstance(val_info, dict):
            continue
        raw_value = val_info.get("value")
        if raw_value is None:
            continue
        try:
            raw_value = float(raw_value)
        except (ValueError, TypeError):
            continue

        unit = val_info.get("unit", "")
        norm_value, norm_unit = normalize_lab_value(raw_value, unit, metric_name)

        # Rule-based detection
        detections = _check_detection_rules(metric_name, norm_value)
        for d in detections:
            d["triggering_metric"] = metric_name
            d["triggering_value"] = norm_value
            detected.append(d)

    # Deduplicate by disease_code
    seen = set()
    unique = []
    for d in detected:
        if d["disease_code"] not in seen:
            seen.add(d["disease_code"])
            unique.append(d)

    return unique


def _check_detection_rules(metric_name: str, value: float) -> list:
    """Check a single metric against detection rules.

    Returns list of detected diseases.
    """
    results = []

    rules = {
        "HbA1c": [
            {"threshold": 6.5, "op": ">", "code": "E11", "name": "Type 2 Diabetes Mellitus",
             "confidence": lambda v: min(0.6 + (v - 6.5) * 0.05, 0.85)},
            {"threshold": 5.7, "op": ">", "code": "E11", "name": "Prediabetes",
             "confidence": lambda v: 0.5}
        ],
        "Fasting Glucose": [
            {"threshold": 126, "op": ">", "code": "E11", "name": "Type 2 Diabetes Mellitus",
             "confidence": lambda v: min(0.55 + (v - 126) * 0.002, 0.8)},
            {"threshold": 100, "op": ">", "code": "E11", "name": "Prediabetes",
             "confidence": lambda v: 0.5}
        ],
        "Post-Prandial Glucose": [
            {"threshold": 200, "op": ">", "code": "E11", "name": "Type 2 Diabetes Mellitus",
             "confidence": lambda v: 0.6}
        ],
        "Systolic BP": [
            {"threshold": 140, "op": ">", "code": "I10", "name": "Hypertension",
             "confidence": lambda v: min(0.6 + (v - 140) * 0.01, 0.8)}
        ],
        "Diastolic BP": [
            {"threshold": 90, "op": ">", "code": "I10", "name": "Hypertension",
             "confidence": lambda v: min(0.6 + (v - 90) * 0.02, 0.8)}
        ],
        "Total Cholesterol": [
            {"threshold": 240, "op": ">", "code": "E78", "name": "Hyperlipidemia",
             "confidence": lambda v: min(0.55 + (v - 240) * 0.003, 0.8)}
        ],
        "LDL": [
            {"threshold": 130, "op": ">", "code": "E78", "name": "Hyperlipidemia",
             "confidence": lambda v: min(0.55 + (v - 130) * 0.003, 0.8)}
        ],
        "Triglycerides": [
            {"threshold": 200, "op": ">", "code": "E78", "name": "Hyperlipidemia",
             "confidence": lambda v: 0.6}
        ],
        "Creatinine": [
            {"threshold": 1.3, "op": ">", "code": "N18", "name": "Chronic Kidney Disease",
             "confidence": lambda v: min(0.5 + (v - 1.3) * 0.1, 0.75)}
        ],
        "eGFR": [
            {"threshold": 60, "op": "<", "code": "N18", "name": "Chronic Kidney Disease",
             "confidence": lambda v: min(0.6 + (60 - v) * 0.005, 0.85)}
        ],
        "TSH": [
            {"threshold": 4.5, "op": ">", "code": "E03", "name": "Hypothyroidism",
             "confidence": lambda v: min(0.55 + (v - 4.5) * 0.03, 0.8)},
            {"threshold": 0.4, "op": "<", "code": "E05", "name": "Hyperthyroidism",
             "confidence": lambda v: min(0.55 + (0.4 - v) * 0.1, 0.8)}
        ],
        "Hemoglobin": [
            {"threshold": 13.0, "op": "<", "code": "D64", "name": "Anemia",
             "confidence": lambda v: min(0.55 + (13.0 - v) * 0.05, 0.8)}
        ],
        "Uric Acid": [
            {"threshold": 7.0, "op": ">", "code": "E87", "name": "Hyperuricemia",
             "confidence": lambda v: min(0.5 + (v - 7.0) * 0.05, 0.75)}
        ],
    }

    if metric_name not in rules:
        return results

    for rule in rules[metric_name]:
        triggered = False
        if rule["op"] == ">" and value > rule["threshold"]:
            triggered = True
        elif rule["op"] == "<" and value < rule["threshold"]:
            triggered = True

        if triggered:
            conf = rule["confidence"](value)
            print(f"[disease_detection] RULE TRIGGERED: {metric_name}={value} matches {rule['name']}")
            results.append({
                "disease_code": rule["code"],
                "disease_name": rule["name"],
                "confidence_score": round(conf, 2),
                "source_type": "lab_inferred",
            })

    return results


# ---------- Full Disease Detection ----------

def detect_diseases_from_report(
    extracted_data: dict,
    existing_conditions: list,
    db: Session,
    report_id: int = None,
    report_date: str = None
) -> list:
    """Detect diseases from a structured report.

    Combines:
    1. Explicit diagnoses from report text
    2. Lab-value inferred diseases

    Deduplicates against existing conditions for this patient.

    Returns:
        List of new disease dicts ready to be stored.
    """
    new_diseases = []
    existing_codes = {c.disease_code for c in existing_conditions}

    report_dt = None
    if report_date:
        try:
            report_dt = datetime.date.fromisoformat(report_date)
        except (ValueError, TypeError):
            report_dt = datetime.date.today()
    else:
        report_dt = datetime.date.today()

    # 1. Explicit diagnoses from the report
    for diag_name in extracted_data.get("diagnoses", []):
        code, canonical_name = _match_disease_code(diag_name)
        if code and code not in existing_codes:
            existing_codes.add(code)
            new_diseases.append({
                "disease_code": code,
                "disease_name": canonical_name,
                "confidence_score": 0.95,
                "source_type": "explicit_diagnosis",
                "first_detected": report_dt,
                "triggering_metric": None,
                "triggering_value": None,
            })

    # 1.5. Resolve explicitly resolved diagnoses
    for diag_name in extracted_data.get("resolved_diagnoses", []):
        code, _ = _match_disease_code(diag_name)
        if code:
            for condition in existing_conditions:
                if condition.disease_code == code and condition.status != ConditionStatus.resolved:
                    prev_status = condition.status
                    condition.status = ConditionStatus.resolved
                    condition.resolved_date = report_dt
                    condition.status_version += 1
                    condition.last_updated = report_dt
                    
                    from tables.medical_conditions import ConditionHistory, ConditionSeverity, ConditionStatus
                    history = ConditionHistory(
                        condition_id=condition.id,
                        report_id=report_id,
                        previous_status=prev_status.value if prev_status else None,
                        new_status=ConditionStatus.resolved.value,
                        previous_severity=condition.severity.value if condition.severity else None,
                        new_severity=ConditionSeverity.mild.value, # Assuming resolved implies mild/no severity
                        status_version=condition.status_version,
                        clinical_interpretation=f"Condition marked as explicitly resolved/cured in medical report.",
                        change_reason=f"Doctor noted resolution on {report_dt}",
                        recorded_at=datetime.datetime.utcnow()
                    )
                    db.add(history)
                    print(f"[disease_detection] Explicitly resolved condition {condition.id} ({diag_name})")

    # 2. Lab-value inferred diseases
    lab_values = extracted_data.get("lab_values", {})
    lab_detected = detect_diseases_from_lab_values(lab_values)
    for d in lab_detected:
        if d["disease_code"] not in existing_codes:
            existing_codes.add(d["disease_code"])
            d["first_detected"] = report_dt
            new_diseases.append(d)

    # 3. Set baseline values from triggering metrics
    for disease in new_diseases:
        if disease.get("triggering_value") is not None:
            disease["baseline_value"] = disease["triggering_value"]
            disease["baseline_date"] = report_dt

    print(f"[disease_detection] Detected {len(new_diseases)} new diseases from report")
    return new_diseases
