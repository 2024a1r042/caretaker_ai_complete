"""Lab Normalizer — Physiological validation, name canonicalization, and unit normalization.

This runs AFTER extraction and BEFORE saving to the database.
It provides:
  1. Canonical metric name mapping (handles aliases like "A1C" → "HbA1c")
  2. Unit normalization (mmol/L → mg/dL, thou/mm3 → 10^3/uL, etc.)
  3. Physiological range guardrails (reject obviously wrong values)
  4. Confidence scoring based on extraction source
"""
from __future__ import annotations
from typing import Optional


# ─── Canonical Name Map ───────────────────────────────────────────────────────
# Maps ALL known aliases/OCR variants → canonical internal name.
# The canonical name must match what already exists in the LabValue table.

METRIC_ALIASES: dict[str, str] = {
    # ── Glucose / Diabetes ─────────────────────────────────────────
    "glucose":                      "Fasting Glucose",
    "blood glucose":                "Fasting Glucose",
    "fasting glucose":              "Fasting Glucose",
    "fasting blood glucose":        "Fasting Glucose",
    "blood sugar fasting":          "Fasting Glucose",
    "glucose, fasting":             "Fasting Glucose",
    "glucose (f)":                  "Fasting Glucose",
    "gluc f":                       "Fasting Glucose",
    "ppbs":                         "Postprandial Glucose",
    "postprandial glucose":         "Postprandial Glucose",
    "blood sugar pp":               "Postprandial Glucose",
    "hba1c":                        "HbA1c",
    "a1c":                          "HbA1c",
    "haemoglobin a1c":              "HbA1c",
    "hemoglobin a1c":               "HbA1c",
    "glycated hemoglobin":          "HbA1c",
    "glycosylated hemoglobin":      "HbA1c",
    "hb a1c":                       "HbA1c",
    "glycohemoglobin":              "HbA1c",
    "gh":                           "HbA1c",
    "hba1c (ifcc)":                 "HbA1c",
    "hba1c, glycated hemoglobin":   "HbA1c",

    # ── Blood Pressure ─────────────────────────────────────────────
    "systolic bp":                  "Systolic BP",
    "systolic blood pressure":      "Systolic BP",
    "systolic":                     "Systolic BP",
    "diastolic bp":                 "Diastolic BP",
    "diastolic blood pressure":     "Diastolic BP",
    "diastolic":                    "Diastolic BP",

    # ── Lipid Panel ────────────────────────────────────────────────
    "total cholesterol":            "Total Cholesterol",
    "cholesterol":                  "Total Cholesterol",
    "cholesterol total":            "Total Cholesterol",
    "s. cholesterol":               "Total Cholesterol",
    "serum cholesterol":            "Total Cholesterol",
    "ldl cholesterol":              "LDL",
    "ldl-c":                        "LDL",
    "low density lipoprotein":      "LDL",
    "hdl cholesterol":              "HDL",
    "hdl-c":                        "HDL",
    "high density lipoprotein":     "HDL",
    "triglycerides":                "Triglycerides",
    "trg":                          "Triglycerides",
    "tg":                           "Triglycerides",
    "vldl cholesterol":             "VLDL",
    "vldl":                         "VLDL",

    # ── Kidney Panel ───────────────────────────────────────────────
    "creatinine":                   "Creatinine",
    "creatinine, serum":            "Creatinine",
    "serum creatinine":             "Creatinine",
    "s. creatinine":                "Creatinine",
    "urea":                         "BUN",
    "blood urea nitrogen":          "BUN",
    "bun":                          "BUN",
    "blood urea":                   "BUN",
    "s. urea":                      "BUN",
    "egfr":                         "eGFR",
    "gfr estimated":                "eGFR",
    "estimated gfr":                "eGFR",
    "uric acid":                    "Uric Acid",
    "serum uric acid":              "Uric Acid",
    "s. uric acid":                 "Uric Acid",
    "microalbumin":                 "Microalbumin",
    "urine microalbumin":           "Microalbumin",

    # ── CBC ────────────────────────────────────────────────────────
    "hemoglobin":                   "Hemoglobin",
    "haemoglobin":                  "Hemoglobin",
    "hb":                           "Hemoglobin",
    "hgb":                          "Hemoglobin",
    "rbc count":                    "RBC",
    "rbc":                          "RBC",
    "red blood cells":              "RBC",
    "wbc count":                    "WBC",
    "wbc":                          "WBC",
    "total leukocyte count":        "WBC",
    "tlc":                          "WBC",
    "white blood cells":            "WBC",
    "platelet count":               "Platelets",
    "platelets":                    "Platelets",
    "plt":                          "Platelets",
    "hematocrit":                   "Hematocrit",
    "haematocrit":                  "Hematocrit",
    "pcv":                          "Hematocrit",
    "mcv":                          "MCV",
    "mch":                          "MCH",
    "mchc":                         "MCHC",
    "rdw-cv":                       "RDW",
    "rdw":                          "RDW",
    "neutrophils":                  "Neutrophils",
    "lymphocytes":                  "Lymphocytes",
    "monocytes":                    "Monocytes",
    "eosinophils":                  "Eosinophils",
    "basophils":                    "Basophils",

    # ── Liver Panel ────────────────────────────────────────────────
    "sgpt":                         "ALT",
    "alt":                          "ALT",
    "alanine aminotransferase":     "ALT",
    "sgpt (alt)":                   "ALT",
    "sgot":                         "AST",
    "ast":                          "AST",
    "aspartate aminotransferase":   "AST",
    "sgot (ast)":                   "AST",
    "alkaline phosphatase":         "ALP",
    "alp":                          "ALP",
    "total bilirubin":              "Bilirubin Total",
    "bilirubin total":              "Bilirubin Total",
    "s. bilirubin":                 "Bilirubin Total",
    "direct bilirubin":             "Bilirubin Direct",
    "bilirubin direct":             "Bilirubin Direct",
    "indirect bilirubin":           "Bilirubin Indirect",
    "total protein":                "Total Protein",
    "s. protein":                   "Total Protein",
    "albumin":                      "Albumin",
    "s. albumin":                   "Albumin",
    "globulin":                     "Globulin",
    "ggtp":                         "GGT",
    "ggt":                          "GGT",
    "gamma-glutamyl transferase":   "GGT",

    # ── Thyroid ────────────────────────────────────────────────────
    "tsh":                          "TSH",
    "thyroid stimulating hormone":  "TSH",
    "t3":                           "T3",
    "triiodothyronine":             "T3",
    "t4":                           "T4",
    "thyroxine":                    "T4",
    "free t3":                      "Free T3",
    "free t4":                      "Free T4",
    "ft3":                          "Free T3",
    "ft4":                          "Free T4",

    # ── Vitamins & Minerals ────────────────────────────────────────
    "vitamin d":                    "Vitamin D",
    "vitamin d, 25-oh":             "Vitamin D",
    "25-oh vitamin d":              "Vitamin D",
    "25-hydroxyvitamin d":          "Vitamin D",
    "vitamin b12":                  "Vitamin B12",
    "b12":                          "Vitamin B12",
    "cobalamin":                    "Vitamin B12",
    "ferritin":                     "Ferritin",
    "serum ferritin":               "Ferritin",
    "iron":                         "Iron",
    "serum iron":                   "Iron",
    "calcium":                      "Calcium",
    "serum calcium":                "Calcium",
    "phosphorus":                   "Phosphorus",
    "potassium":                    "Potassium",
    "s. potassium":                 "Potassium",
    "sodium":                       "Sodium",
    "s. sodium":                    "Sodium",
    "chloride":                     "Chloride",

    # ── Inflammatory / Other ───────────────────────────────────────
    "crp":                          "CRP",
    "c-reactive protein":           "CRP",
    "esr":                          "ESR",
    "erythrocyte sedimentation rate": "ESR",
}


# ─── Unit Normalization ───────────────────────────────────────────────────────
# Maps raw captured units to standard internal strings.

UNIT_NORMALIZE: dict[str, str] = {
    "mg/dl":            "mg/dL",
    "mg/dL":            "mg/dL",
    "mmol/l":           "mmol/L",
    "mmol/L":           "mmol/L",
    "g/dl":             "g/dL",
    "g/dL":             "g/dL",
    "g/l":              "g/L",
    "%":                "%",
    "iu/ml":            "IU/mL",
    "iu/l":             "IU/L",
    "u/l":              "U/L",
    "mu/l":             "mIU/L",
    "uiu/ml":           "µIU/mL",
    "miu/ml":           "mIU/mL",
    "miu/l":            "mIU/L",
    "ng/dl":            "ng/dL",
    "ng/ml":            "ng/mL",
    "pg/ml":            "pg/mL",
    "nmol/l":           "nmol/L",
    "pmol/l":           "pmol/L",
    "meq/l":            "mEq/L",
    "ml/min":           "mL/min",
    "ml/min/1.73m2":    "mL/min/1.73m²",
    "thou/mm3":         "10³/µL",
    "10^3/ul":          "10³/µL",
    "10^3/µl":          "10³/µL",
    "mill/mm3":         "10⁶/µL",
    "10^6/ul":          "10⁶/µL",
    "fl":               "fL",
    "pg":               "pg",
    "mm/hr":            "mm/hr",
    "mg/l":             "mg/L",
    "mcg/dl":           "µg/dL",
    "µg/dl":            "µg/dL",
}


# ─── Physiological Guard Rails (min, max) ─────────────────────────────────────
# Values outside these ranges are almost certainly OCR errors or hallucinations.

PHYSIOLOGICAL_LIMITS: dict[str, tuple[float, float]] = {
    "HbA1c":                (3.0,    20.0),
    "Fasting Glucose":      (50.0,   600.0),
    "Postprandial Glucose": (50.0,   800.0),
    "Total Cholesterol":    (50.0,   600.0),
    "LDL":                  (20.0,   400.0),
    "HDL":                  (10.0,   150.0),
    "Triglycerides":        (20.0,   1500.0),
    "VLDL":                 (5.0,    200.0),
    "Creatinine":           (0.1,    20.0),
    "BUN":                  (2.0,    200.0),
    "eGFR":                 (1.0,    200.0),
    "Uric Acid":            (1.0,    20.0),
    "Hemoglobin":           (3.0,    25.0),
    "RBC":                  (1.0,    10.0),
    "WBC":                  (0.5,    100.0),
    "Platelets":            (10.0,   2000.0),
    "Hematocrit":           (10.0,   65.0),
    "MCV":                  (50.0,   130.0),
    "MCH":                  (10.0,   50.0),
    "MCHC":                 (20.0,   40.0),
    "Neutrophils":          (0.0,    100.0),
    "Lymphocytes":          (0.0,    100.0),
    "Monocytes":            (0.0,    30.0),
    "Eosinophils":          (0.0,    60.0),
    "Basophils":            (0.0,    10.0),
    "ALT":                  (1.0,    5000.0),
    "AST":                  (1.0,    5000.0),
    "ALP":                  (10.0,   3000.0),
    "Bilirubin Total":      (0.1,    30.0),
    "Bilirubin Direct":     (0.0,    20.0),
    "GGT":                  (1.0,    1000.0),
    "Total Protein":        (3.0,    12.0),
    "Albumin":              (1.0,    7.0),
    "TSH":                  (0.001,  100.0),
    "T3":                   (0.1,    15.0),
    "T4":                   (1.0,    30.0),
    "Free T3":              (0.5,    20.0),
    "Free T4":              (0.1,    6.0),
    "Vitamin D":            (1.0,    200.0),
    "Vitamin B12":          (10.0,   5000.0),
    "Ferritin":             (1.0,    10000.0),
    "Iron":                 (10.0,   400.0),
    "Calcium":              (4.0,    15.0),
    "Sodium":               (100.0,  180.0),
    "Potassium":            (1.5,    8.0),
    "CRP":                  (0.0,    500.0),
    "ESR":                  (0.0,    150.0),
    "Systolic BP":          (60.0,   260.0),
    "Diastolic BP":         (30.0,   160.0),
    "Microalbumin":         (0.0,    3000.0),
}


# ─── Unit Conversion ──────────────────────────────────────────────────────────
# (metric_name, from_unit) → (multiplier, to_unit)
# Converted value = raw_value * multiplier

UNIT_CONVERSIONS: dict[tuple[str, str], tuple[float, str]] = {
    ("Fasting Glucose", "mmol/L"):      (18.0,   "mg/dL"),
    ("Postprandial Glucose", "mmol/L"): (18.0,   "mg/dL"),
    ("Total Cholesterol", "mmol/L"):    (38.67,  "mg/dL"),
    ("LDL", "mmol/L"):                  (38.67,  "mg/dL"),
    ("HDL", "mmol/L"):                  (38.67,  "mg/dL"),
    ("Triglycerides", "mmol/L"):        (88.57,  "mg/dL"),
    ("Creatinine", "µmol/L"):           (0.0113, "mg/dL"),
    ("Uric Acid", "µmol/L"):            (0.0168, "mg/dL"),
    ("Vitamin D", "nmol/L"):            (0.4006, "ng/mL"),
}


# ─── Confidence Score ─────────────────────────────────────────────────────────

def confidence_for_source(source: str) -> float:
    """Return extraction confidence score based on source method."""
    return {
        "regex":    0.95,
        "fuzzy":    0.82,
        "llm":      0.65,
        "template": 0.98,   # Template-matched columns (highest)
    }.get(source, 0.70)


# ─── Name Canonicalization ────────────────────────────────────────────────────

def canonicalize_metric_name(raw_name: str) -> Optional[str]:
    """Map a raw metric name to its canonical form.

    Tries:
      1. Direct lower-case lookup
      2. Strip trailing punctuation / numbers / units
      3. Return None if unmappable
    """
    if not raw_name:
        return None
        
    normalized = raw_name.strip().lower()
    
    # ── Layer 1: Clean known pollution ──
    # Strip common OCR trailing junk: "Creatinine 0.95 mg/dl" -> "Creatinine"
    import re
    cleaned = re.sub(r"\s+[\d\.].*$", "", normalized).strip() # Stop at first number
    cleaned = re.sub(r"\s+\(.*\)\s*$", "", cleaned).strip()   # Drop trailing parens
    cleaned = cleaned.rstrip(".,;:- ")
    
    # ── Layer 2: Direct match ──
    if cleaned in METRIC_ALIASES:
        return METRIC_ALIASES[cleaned]
        
    # ── Layer 3: Legacy lookups ──
    if normalized in METRIC_ALIASES:
        return METRIC_ALIASES[normalized]
        
    return None


def canonicalize_metric_name_fuzzy(raw_name: str) -> Optional[tuple[str, float]]:
    """Like canonicalize_metric_name but uses rapidfuzz for typo tolerance.

    Returns (canonical_name, match_score) or None if below threshold.
    """
    try:
        from rapidfuzz import process, fuzz
    except ImportError:
        return None

    normalized = raw_name.strip().lower()
    result = process.extractOne(
        normalized,
        list(METRIC_ALIASES.keys()),
        scorer=fuzz.token_sort_ratio,
        score_cutoff=80,    # ≥80% similarity required
    )
    if result:
        matched_alias, score, _ = result
        return METRIC_ALIASES[matched_alias], score / 100.0
    return None


# ─── Unit Normalization ───────────────────────────────────────────────────────

def normalize_unit(raw_unit: str) -> str:
    """Normalize a raw unit string to its canonical form."""
    if not raw_unit:
        return ""
    key = raw_unit.strip().lower()
    result = UNIT_NORMALIZE.get(key) or UNIT_NORMALIZE.get(raw_unit.strip())
    return result or raw_unit.strip()


# ─── Unit Conversion ──────────────────────────────────────────────────────────

def convert_unit_if_needed(
    metric_name: str, value: float, unit: str
) -> tuple[float, str]:
    """Convert value to standard unit if a conversion rule exists.

    Returns (normalized_value, normalized_unit).
    """
    norm_unit = normalize_unit(unit)
    key = (metric_name, norm_unit)
    if key in UNIT_CONVERSIONS:
        multiplier, target_unit = UNIT_CONVERSIONS[key]
        return round(value * multiplier, 4), target_unit
    return value, norm_unit


# ─── Validation ───────────────────────────────────────────────────────────────

def is_physiologically_valid(metric_name: str, value: float, unit: str) -> bool:
    """Return True if the value is within physiologically plausible limits."""
    limits = PHYSIOLOGICAL_LIMITS.get(metric_name)
    if limits is None:
        # Unknown metric — pass through (don't block)
        return True
    lo, hi = limits
    return lo <= value <= hi


# ─── Main Validation Pipeline Entry ──────────────────────────────────────────

def normalize_and_validate(
    raw_name: str,
    raw_value: float,
    raw_unit: str,
    source: str = "regex",
    db: Session = None,
) -> Optional[dict]:
    """Run the full normalization + validation for a single extracted lab value.
    
    Industry-level design:
    - Checks static ALIASES
    - Checks database MAPPINGS (LabParameterMapping)
    - Checks fuzzy matching
    - FLAGS instead of REJECTS (mostly)
    """
    # ── Step 1: Canonicalize name ───────────────────────────────────────────
    canonical = canonicalize_metric_name(raw_name)
    extraction_source = source
    fuzzy_score = None
    is_mapped = True
    needs_review = False

    if canonical is None:
        # Check DB mappings if session provided
        if db:
            from tables.medical_conditions import LabParameterMapping
            db_map = db.query(LabParameterMapping).filter(
                LabParameterMapping.raw_name == raw_name
            ).first()
            if db_map:
                canonical = db_map.canonical_name
        
        if not canonical:
            # Try fuzzy
            fuzzy_result = canonicalize_metric_name_fuzzy(raw_name)
            if fuzzy_result:
                canonical, fuzzy_score = fuzzy_result
                extraction_source = "fuzzy"
            else:
                # Still no match? Save as-is but flag as unmapped
                canonical = raw_name.strip()
                is_mapped = False

    # ── Step 2: Normalize unit and convert if needed ────────────────────────
    # If unmapped, skip conversion
    norm_value, norm_unit = raw_value, normalize_unit(raw_unit)
    if is_mapped:
        norm_value, norm_unit = convert_unit_if_needed(canonical, raw_value, raw_unit)

    # ── Step 3: Physiological validation ────────────────────────────────────
    if is_mapped and not is_physiologically_valid(canonical, norm_value, norm_unit):
        print(f"[normalizer] ⚠️ Flagging outlier: {canonical}={norm_value} {norm_unit}")
        needs_review = True  # Flag it but allow storage

    # ── Step 4: Confidence score ────────────────────────────────────────────
    conf = confidence_for_source(extraction_source)
    if fuzzy_score and extraction_source == "fuzzy":
        conf = min(conf, fuzzy_score)

    return {
        "metric_name":      canonical,
        "metric_value":     raw_value,
        "unit":             raw_unit,
        "normalized_value": norm_value,
        "normalized_unit":  norm_unit,
        "confidence_score": round(conf, 3),
        "extraction_source": extraction_source,
        "is_mapped":        is_mapped,
        "needs_review":     needs_review,
    }
