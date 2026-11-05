from sqlalchemy import Column, Integer, String, Float, JSON
from config import Base


class DiseaseDictionary(Base):
    """ICD-style normalized disease catalog.

    Stores detection rules, status transition rules, monitoring config,
    and alert throttling parameters for each known disease.
    """
    __tablename__ = "disease_dictionary"

    code = Column(String, primary_key=True, index=True)             # ICD-style, e.g. "E11"
    name = Column(String, nullable=False, unique=True)              # e.g. "Type 2 Diabetes Mellitus"
    category = Column(String, nullable=True)                        # e.g. "Endocrine"

    # Metrics this disease tracks (JSON list)
    # e.g. ["HbA1c", "Fasting Glucose"]
    monitoring_metrics = Column(JSON, nullable=True)

    # Rules for auto-detecting from lab values (JSON)
    # e.g. {"HbA1c": {"operator": ">", "threshold": 6.5}, ...}
    detection_rules = Column(JSON, nullable=True)

    # Rules for status transitions (JSON)
    # e.g. {"poor_control": {"HbA1c": {">": 8}}, "controlled": {"HbA1c": {"<": 6.5}}, ...}
    status_rules = Column(JSON, nullable=True)

    # Alert throttling config
    alert_cooldown_days = Column(Integer, default=7)                # Min days between alerts
    minimum_change_threshold = Column(Float, default=5.0)           # % change to trigger alert

    # Disease-specific monitoring interval (months)
    monitoring_frequency_months = Column(Integer, default=6)        # e.g. 3 for uncontrolled diabetes

    # Unit conversion rules for this disease's metrics (JSON)
    # e.g. {"Glucose": {"mmol/L": {"multiply": 18.018, "target_unit": "mg/dL"}}}
    unit_conversions = Column(JSON, nullable=True)


# ---------- Seed Data ----------

DISEASE_SEED_DATA = [
    {
        "code": "E11",
        "name": "Type 2 Diabetes Mellitus",
        "category": "Endocrine",
        "monitoring_metrics": ["HbA1c", "Fasting Glucose", "Post-Prandial Glucose"],
        "detection_rules": {
            "HbA1c": {"operator": ">", "threshold": 6.5, "unit": "%"},
            "Fasting Glucose": {"operator": ">", "threshold": 126, "unit": "mg/dL"}
        },
        "status_rules": {
            "worsening": {"HbA1c": {">": 8.0}},
            "moderate": {"HbA1c": {">=": 6.5, "<": 8.0}},
            "controlled": {"HbA1c": {"<": 6.5}},
            "resolved": {"HbA1c": {"<": 6.0}, "consecutive_normal": 3}
        },
        "alert_cooldown_days": 7,
        "minimum_change_threshold": 5.0,
        "monitoring_frequency_months": 3,
        "unit_conversions": {
            "Fasting Glucose": {
                "mmol/L": {"multiply": 18.018, "target_unit": "mg/dL"}
            },
            "Post-Prandial Glucose": {
                "mmol/L": {"multiply": 18.018, "target_unit": "mg/dL"}
            }
        }
    },
    {
        "code": "I10",
        "name": "Hypertension",
        "category": "Cardiovascular",
        "monitoring_metrics": ["Systolic BP", "Diastolic BP"],
        "detection_rules": {
            "Systolic BP": {"operator": ">", "threshold": 140, "unit": "mmHg"},
            "Diastolic BP": {"operator": ">", "threshold": 90, "unit": "mmHg"}
        },
        "status_rules": {
            "worsening": {"Systolic BP": {">": 160}},
            "moderate": {"Systolic BP": {">=": 140, "<": 160}},
            "controlled": {"Systolic BP": {"<": 140}},
            "resolved": {"Systolic BP": {"<": 120}, "Diastolic BP": {"<": 80}, "consecutive_normal": 3}
        },
        "alert_cooldown_days": 7,
        "minimum_change_threshold": 10.0,
        "monitoring_frequency_months": 6,
        "unit_conversions": {}
    },
    {
        "code": "E78",
        "name": "Hyperlipidemia",
        "category": "Metabolic",
        "monitoring_metrics": ["Total Cholesterol", "LDL", "HDL", "Triglycerides"],
        "detection_rules": {
            "Total Cholesterol": {"operator": ">", "threshold": 240, "unit": "mg/dL"},
            "LDL": {"operator": ">", "threshold": 160, "unit": "mg/dL"}
        },
        "status_rules": {
            "worsening": {"Total Cholesterol": {">": 280}},
            "moderate": {"Total Cholesterol": {">=": 200, "<": 280}},
            "controlled": {"Total Cholesterol": {"<": 200}},
            "resolved": {"Total Cholesterol": {"<": 200}, "LDL": {"<": 130}, "consecutive_normal": 3}
        },
        "alert_cooldown_days": 14,
        "minimum_change_threshold": 10.0,
        "monitoring_frequency_months": 6,
        "unit_conversions": {
            "Total Cholesterol": {
                "mmol/L": {"multiply": 38.67, "target_unit": "mg/dL"}
            },
            "LDL": {
                "mmol/L": {"multiply": 38.67, "target_unit": "mg/dL"}
            },
            "HDL": {
                "mmol/L": {"multiply": 38.67, "target_unit": "mg/dL"}
            },
            "Triglycerides": {
                "mmol/L": {"multiply": 88.57, "target_unit": "mg/dL"}
            }
        }
    },
    {
        "code": "D64",
        "name": "Anemia",
        "category": "Hematologic",
        "monitoring_metrics": ["Hemoglobin", "Hematocrit", "Ferritin"],
        "detection_rules": {
            "Hemoglobin": {"operator": "<", "threshold": 12.0, "unit": "g/dL"}
        },
        "status_rules": {
            "worsening": {"Hemoglobin": {"<": 10.0}},
            "moderate": {"Hemoglobin": {">=": 10.0, "<": 12.0}},
            "controlled": {"Hemoglobin": {">=": 12.0}},
            "resolved": {"Hemoglobin": {">=": 12.0}, "consecutive_normal": 3}
        },
        "alert_cooldown_days": 7,
        "minimum_change_threshold": 8.0,
        "monitoring_frequency_months": 3,
        "unit_conversions": {}
    },
    {
        "code": "N18",
        "name": "Chronic Kidney Disease",
        "category": "Renal",
        "monitoring_metrics": ["Creatinine", "eGFR", "BUN"],
        "detection_rules": {
            "Creatinine": {"operator": ">", "threshold": 1.3, "unit": "mg/dL"},
            "eGFR": {"operator": "<", "threshold": 60, "unit": "mL/min"}
        },
        "status_rules": {
            "worsening": {"Creatinine": {">": 2.0}},
            "moderate": {"Creatinine": {">=": 1.3, "<": 2.0}},
            "controlled": {"Creatinine": {"<": 1.3}},
            "resolved": {"Creatinine": {"<": 1.2}, "consecutive_normal": 3}
        },
        "alert_cooldown_days": 5,
        "minimum_change_threshold": 10.0,
        "monitoring_frequency_months": 3,
        "unit_conversions": {
            "Creatinine": {
                "µmol/L": {"multiply": 0.0113, "target_unit": "mg/dL"},
                "umol/L": {"multiply": 0.0113, "target_unit": "mg/dL"}
            }
        }
    },
    {
        "code": "E03",
        "name": "Hypothyroidism",
        "category": "Endocrine",
        "monitoring_metrics": ["TSH", "T3", "T4"],
        "detection_rules": {
            "TSH": {"operator": ">", "threshold": 4.5, "unit": "mIU/L"}
        },
        "status_rules": {
            "worsening": {"TSH": {">": 10.0}},
            "moderate": {"TSH": {">=": 4.5, "<": 10.0}},
            "controlled": {"TSH": {"<": 4.5}},
            "resolved": {"TSH": {">=": 0.4, "<": 4.5}, "consecutive_normal": 3}
        },
        "alert_cooldown_days": 14,
        "minimum_change_threshold": 15.0,
        "monitoring_frequency_months": 6,
        "unit_conversions": {}
    },
    {
        "code": "E05",
        "name": "Hyperthyroidism",
        "category": "Endocrine",
        "monitoring_metrics": ["TSH", "T3", "T4"],
        "detection_rules": {
            "TSH": {"operator": "<", "threshold": 0.4, "unit": "mIU/L"}
        },
        "status_rules": {
            "worsening": {"TSH": {"<": 0.1}},
            "moderate": {"TSH": {">=": 0.1, "<": 0.4}},
            "controlled": {"TSH": {">=": 0.4}},
            "resolved": {"TSH": {">=": 0.4, "<": 4.5}, "consecutive_normal": 3}
        },
        "alert_cooldown_days": 14,
        "minimum_change_threshold": 15.0,
        "monitoring_frequency_months": 6,
        "unit_conversions": {}
    },
    {
        "code": "E87",
        "name": "Hyperuricemia",
        "category": "Metabolic",
        "monitoring_metrics": ["Uric Acid"],
        "detection_rules": {
            "Uric Acid": {"operator": ">", "threshold": 7.0, "unit": "mg/dL"}
        },
        "status_rules": {
            "worsening": {"Uric Acid": {">": 9.0}},
            "moderate": {"Uric Acid": {">=": 7.0, "<": 9.0}},
            "controlled": {"Uric Acid": {"<": 7.0}},
            "resolved": {"Uric Acid": {"<": 6.0}, "consecutive_normal": 3}
        },
        "alert_cooldown_days": 14,
        "minimum_change_threshold": 10.0,
        "monitoring_frequency_months": 6,
        "unit_conversions": {}
    },
]


def seed_disease_dictionary(db_session):
    """Seed disease dictionary if empty. Idempotent — skips already-existing codes."""
    existing_codes = {
        row.code for row in db_session.query(DiseaseDictionary.code).all()
    }
    added = 0
    for entry in DISEASE_SEED_DATA:
        if entry["code"] not in existing_codes:
            db_session.add(DiseaseDictionary(**entry))
            added += 1
    if added:
        db_session.commit()
        print(f"[disease_dictionary] Seeded {added} disease entries")
    else:
        print("[disease_dictionary] Disease dictionary already populated")
