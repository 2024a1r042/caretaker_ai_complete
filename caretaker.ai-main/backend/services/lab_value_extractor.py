"""
Rule-based lab value extractor — works WITHOUT Gemini.

Parses common lab test patterns from medical report text using regex.
Supports standard Indian diagnostic lab report formats.

Returns the same `lab_values` dict structure as Gemini:
  { "MetricName": {"value": 8.2, "unit": "%"}, ... }
"""

import re
from datetime import date


# ---------------------------------------------------------------------------
# Canonical metric aliases — maps any variant spelling → canonical name
# ---------------------------------------------------------------------------
METRIC_ALIASES = {
    # Blood glucose
    r"fasting\s*(blood\s*)?(glucose|sugar|bs)": "Fasting Glucose",
    r"pp\s*(blood\s*)?(glucose|sugar|bs)": "PP Glucose",
    r"hba1c|hb\s*a1c|glycated\s*haemoglobin|glycosylated\s*hemoglobin": "HbA1c",
    r"random\s*(blood\s*)?(glucose|sugar)": "Random Glucose",

    # Lipids
    r"total\s*cholesterol": "Total Cholesterol",
    r"ldl[\s\-]*(c|cholesterol)?": "LDL",
    r"hdl[\s\-]*(c|cholesterol)?": "HDL",
    r"triglycerides?|tg": "Triglycerides",
    r"vldl[\s\-]*(c|cholesterol)?": "VLDL",

    # Liver
    r"alt|sgpt|alanine\s*aminotransferase": "ALT",
    r"ast|sgot|aspartate\s*aminotransferase": "AST",
    r"alp|alkaline\s*phosphatase": "ALP",
    r"ggt|gamma[\s\-]*gt|gamma[\s\-]*glutamyl": "GGT",
    r"bilirubin[\s,\-]*(total)?": "Bilirubin Total",
    r"bilirubin[\s,\-]*direct": "Bilirubin Direct",
    r"bilirubin[\s,\-]*indirect": "Bilirubin Indirect",
    r"albumin": "Albumin",
    r"total\s*protein": "Total Protein",

    # Kidney
    r"creatinine": "Creatinine",
    r"urea|bun|blood\s*urea(\s*nitrogen)?": "BUN",
    r"uric\s*acid": "Uric Acid",
    r"egfr|estimated\s*gfr": "eGFR",

    # Thyroid
    r"tsh|thyroid\s*stimulating\s*hormone": "TSH",
    r"\bft3\b|free\s*t3|triiodothyronine": "T3",
    r"\bft4\b|free\s*t4|thyroxine": "T4",

    # CBC
    r"hemoglobin|haemoglobin|\bhb\b|\bhgb\b": "Hemoglobin",
    r"hematocrit|haematocrit|\bhct\b|\bpcv\b": "Hematocrit",
    r"wbc|white\s*blood\s*(cell|count)|leukocyte": "WBC",
    r"rbc|red\s*blood\s*(cell|count)": "RBC",
    r"platelets?|plt": "Platelets",
    r"mcv": "MCV",
    r"mch\b": "MCH",
    r"mchc": "MCHC",

    # Iron
    r"serum\s*iron|iron[\s,]*serum": "Serum Iron",
    r"ferritin": "Ferritin",
    r"tibc|total\s*iron\s*binding": "TIBC",

    # Electrolytes
    r"sodium|na\+?": "Sodium",
    r"potassium|k\+?": "Potassium",
    r"chloride|cl\-?": "Chloride",
    r"calcium|ca\+?": "Calcium",
    r"magnesium|mg\+?": "Magnesium",
    r"phosphorus|phosphate": "Phosphorus",

    # Blood pressure (sometimes in lab reports)
    r"systolic\s*(bp|blood\s*pressure)": "Systolic BP",
    r"diastolic\s*(bp|blood\s*pressure)": "Diastolic BP",

    # Vitamins
    r"vitamin\s*d(\s*(total|25[\s\-]*oh))?|25[\s\-]*oh[\s\-]*vitamin\s*d": "Vitamin D",
    r"vitamin\s*b12|cobalamin": "Vitamin B12",
    r"folate|folic\s*acid": "Folate",

    # Other
    r"esr|erythrocyte\s*sedimentation": "ESR",
    r"crp|c[\s\-]*reactive\s*protein": "CRP",
    r"psa|prostate[\s\-]*specific\s*antigen": "PSA",
    r"hiv": "HIV",
}

# Numeric value and unit pattern — handles: 8.2 %, 180mg/dL, 6.2%, 45 U/L
VALUE_UNIT_PATTERN = r"([\d]+\.?[\d]*)\s*([a-zA-Z%\/\*]+(?:\s*/\s*[a-zA-Z\*]+)?)"

# Common units — helps validate matches
KNOWN_UNITS = {
    "%", "mg/dl", "mg/dl", "mmol/l", "u/l", "iu/l", "miu/l",
    "g/dl", "g/l", "ng/ml", "ng/dl", "pg/ml", "ug/ml", "ug/dl",
    "meq/l", "meq/dl", "mmhg", "fL", "fl", "cells/ul", "cells/cumm",
    "thousands/ul", "lacs", "lakhs", "10^3", "10^6", "mu/l",
    "pmol/l", "nmol/l", "umol/l", "seconds", "sec"
}


def _normalize_unit(unit_str: str) -> str:
    """Normalize unit string for storage."""
    u = unit_str.strip().lower().replace(" ", "")
    mappings = {
        "mg/dl": "mg/dL", "mg/dl.": "mg/dL",
        "mmol/l": "mmol/L",
        "g/dl": "g/dL",
        "u/l": "U/L", "iu/l": "IU/L", "miu/l": "mIU/L",
        "ng/ml": "ng/mL", "ng/dl": "ng/dL",
        "pg/ml": "pg/mL",
        "ug/ml": "ug/mL", "μg/ml": "ug/mL",
        "meq/l": "mEq/L",
        "fl": "fL",
        "%": "%",
    }
    return mappings.get(u, unit_str.strip())


def _resolve_metric_name(raw_name: str) -> str | None:
    """Map a raw metric name to its canonical form, or None if unrecognised."""
    cleaned = raw_name.strip().lower()
    for pattern, canonical in METRIC_ALIASES.items():
        if re.fullmatch(pattern, cleaned, re.IGNORECASE):
            return canonical
    return None


def _extract_date(text: str) -> str | None:
    """Try to extract a date from the report text."""
    patterns = [
        # "10 Mar 2026", "10-Mar-2026", "10/Mar/2026"
        r"\b(\d{1,2}[\s\-/](?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s\-/]\d{4})\b",
        # "2026-03-10", "10-03-2026", "10/03/2026"
        r"\b(\d{4}[\-/]\d{2}[\-/]\d{2})\b",
        r"\b(\d{2}[\-/]\d{2}[\-/]\d{4})\b",
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            raw = m.group(1)
            # Try to normalize to YYYY-MM-DD
            try:
                import dateutil.parser
                return str(dateutil.parser.parse(raw, dayfirst=True).date())
            except Exception:
                pass
            return raw
    return None


def extract_lab_values_from_text(text: str, report_date_hint: str = None) -> dict:
    """
    Rule-based extraction of lab values from raw medical report text.

    Strategy:
    1. Split text into lines
    2. For each line, try to match: <metric_name> ... <value> <unit>
    3. Normalize metric name via METRIC_ALIASES
    4. Return dict in same format as Gemini: {"MetricName": {"value": X, "unit": "Y"}}

    Also extracts report_date using regex.
    """
    result = {
        "report_date": report_date_hint or str(date.today()),
        "lab_values": {},
        # These fields require Gemini — left empty for rule-based extraction
        "diagnoses": [],
        "resolved_diagnoses": [],
        "medications": [],
        "doctor_notes": "",
        "symptoms": [],
        "_source": "rule_based",  # marker so we know Gemini insights are pending
    }

    if not text:
        return result

    # Try to get date from text
    extracted_date = _extract_date(text)
    if extracted_date:
        result["report_date"] = extracted_date

    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        if not line or len(line) < 3:
            continue

        # Pattern A: "MetricName : 45.2 U/L" or "MetricName 45.2 U/L"
        # Broadly: <text up to colon or space> <number> <unit>
        match = re.match(
            r"^([A-Za-z][A-Za-z0-9\s\(\)\-\*\/\.]{2,60?}?)\s*[:\-]?\s*"
            r"([\d]+\.?[\d]*)\s*([A-Za-z%\*\/\.]+(?:\/[A-Za-z\*\.]+)?)\s*$",
            line
        )
        if not match:
            # Pattern B: inline style "Total Cholesterol: 180 mg/dL" within larger text
            matches = re.findall(
                r"([A-Za-z][A-Za-z0-9\s\(\)\-]{2,40}?)\s*[:\-]\s*([\d]+\.?[\d]*)\s*([A-Za-z%\*\/]{1,12})",
                line
            )
            for raw_name, val_str, unit_str in matches:
                canon = _resolve_metric_name(raw_name)
                if canon:
                    try:
                        result["lab_values"][canon] = {
                            "value": float(val_str),
                            "unit": _normalize_unit(unit_str)
                        }
                    except ValueError:
                        pass
            continue

        raw_name, val_str, unit_str = match.group(1), match.group(2), match.group(3)
        canon = _resolve_metric_name(raw_name)
        if canon:
            try:
                result["lab_values"][canon] = {
                    "value": float(val_str),
                    "unit": _normalize_unit(unit_str)
                }
            except ValueError:
                pass

    count = len(result["lab_values"])
    if count:
        print(f"[lab_extractor] ✅ Rule-based: extracted {count} lab values: {list(result['lab_values'].keys())}")
    else:
        print("[lab_extractor] ⚠️  Rule-based: no lab values matched — will rely on Gemini")

    return result
