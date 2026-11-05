"""Lab Parser — Core extraction engine for medical report text.

Architecture (applied in order):
  1. Template Detection       → chooses the right parsing strategy
  2. Section Segmentation     → splits text into named clinical sections
  3. Row-Level Rule Extraction → regex pattern matches on each line
  4. Fuzzy + Alias Matching   → handles OCR typos via lab_normalizer
  5. LLM Fallback             → only for lines that fail layers 1–4

This module returns raw extracted rows. Normalization and validation are
handled separately by lab_normalizer.py.
"""
from __future__ import annotations

import re
from typing import Optional
from services.document_cleaner import clean_document, is_section_header


# ══════════════════════════════════════════════════════════════════════════════
# 1. TEMPLATE DETECTION
# ══════════════════════════════════════════════════════════════════════════════

TEMPLATES = {
    "LALPATH": [
        "lal pathlabs",
        "dr. lal pathlabs",
        "dr lal path",
        "lalpathlabs",
    ],
    "THYROCARE": [
        "thyrocare",
    ],
    "SRL": [
        "srl diagnostics",
        "srl ltd",
    ],
    "SIMPLE_AI": [
        "diagnostic laboratory test report",
        "lab report",
    ],
}


def detect_template(text: str) -> str:
    """Return the best-matching template ID for the document, or 'GENERIC'."""
    sample = text[:2000].lower()
    for template_id, signatures in TEMPLATES.items():
        for sig in signatures:
            if sig in sample:
                return template_id
    return "GENERIC"


# ══════════════════════════════════════════════════════════════════════════════
# 2. SECTION SEGMENTATION
# ══════════════════════════════════════════════════════════════════════════════

# Known clinical section keywords. The parser tracks the active section so
# each extracted row is tagged with its source section.
SECTION_KEYWORDS = [
    "LIVER",
    "KIDNEY",
    "RENAL",
    "LIPID",
    "GLUCOSE",
    "DIABETES",
    "THYROID",
    "CBC",
    "COMPLETE BLOOD",
    "HAEMATOLOGY",
    "HEMATOLOGY",
    "VITAMIN",
    "ELECTROLYTE",
    "IRON",
    "CARDIAC",
    "INFLAMMATORY",
    "COAGULATION",
    "URINE",
    "HBA1C",
    "GLYCATED",
    "INFLAMMATION",
]


def classify_section(line: str) -> Optional[str]:
    """Return a section label if this line looks like a clinical section header."""
    if not is_section_header(line):
        return None
    upper = line.upper()
    for kw in SECTION_KEYWORDS:
        if kw in upper:
            return line.strip()
    # Still a section header even if unknown keyword
    return line.strip()


# ══════════════════════════════════════════════════════════════════════════════
# 3. ROW-LEVEL RULE EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

# Master pattern:  TestName   Value   [Unit]   [Reference]
# Refined to stop capturing name as soon as a numeric-ish value is found.
_MASTER_LAB = re.compile(
    r"^\s*[\*\|-]?\s*"                                 # Optional leading bullet, pipe, or dash
    r"(?P<name>[A-Za-z0-9][A-Za-z0-9 /(),\-\.]{1,40}?(?=:?\s*[<>]?\d))" # Non-greedy name, stops before value
    r"\s*[:\-]?\s*"                                    # Separator (colon, dash, or whitespace)
    r"(?P<value>[<>]?\d+(?:\.\d+)?)"                   # Numeric value
    r"(?:\s+(?P<unit>[A-Za-z%/^µ³²·\d\.]+(?:/[A-Za-z³²µ\d\.]+)?))?"  # Optional Unit
    r"(?:\s+(?P<range>[<>]?\d[\d\.\-\s<>]+))?",        # Optional reference range
    re.IGNORECASE,
)

# Blood Pressure: "120/80" (systolic/diastolic on same line)
_BP_PATTERN = re.compile(
    r"(?:bp|blood pressure|b\.p\.)\s*[:\-]?\s*"
    r"(?P<systolic>\d{2,3})/(?P<diastolic>\d{2,3})",
    re.IGNORECASE,
)

# Inline-range pattern: "HbA1c: 8.2%" or "TSH=2.45"
_INLINE_LABELED = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9 /(),\-\.]{2,30})"
    r"\s*[:\-=]\s*"
    r"(?P<value>[<>]?\d+(?:\.\d+)?)\s*"
    r"(?P<unit>[A-Za-z%/µ³²·\d\.]+(?:/[A-Za-z³²µ\d\.]+)?)?",
    re.IGNORECASE,
)

# Simple value-only after name (for "| HbA1c | 8.2 |" table rows)
_TABLE_SPLIT = re.compile(r"\|")


def _parse_range(range_str: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """Parse a reference range like '0.70 - 1.30' or '>59' into (low, high)."""
    if not range_str:
        return None, None
    range_str = range_str.strip()
    # Greater-than form: ">59"
    m = re.match(r"^>\s*(\d+(?:\.\d+)?)$", range_str)
    if m:
        return float(m.group(1)), None
    # Less-than form: "<200"
    m = re.match(r"^<\s*(\d+(?:\.\d+)?)$", range_str)
    if m:
        return None, float(m.group(1))
    # Range form: "0.70 - 1.30" or "0.70 – 1.30"
    m = re.match(
        r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)",
        range_str,
    )
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


def _extract_from_master(line: str) -> Optional[dict]:
    """Try the master lab pattern on a single line."""
    m = _MASTER_LAB.match(line)
    if not m:
        return None
    value_str = m.group("value").lstrip("<>").strip()
    try:
        value = float(value_str)
    except ValueError:
        return None
    ref_low, ref_high = _parse_range(m.group("range"))
    return {
        "raw_name":  m.group("name").strip(),
        "value":     value,
        "unit":      (m.group("unit") or "").strip(),
        "ref_low":   ref_low,
        "ref_high":  ref_high,
        "source":    "regex",
    }


def _extract_bp(line: str) -> list[dict]:
    """Extract blood pressure readings from a line."""
    results = []
    for m in _BP_PATTERN.finditer(line):
        results.append({
            "raw_name": "Systolic BP",
            "value":    float(m.group("systolic")),
            "unit":     "mmHg",
            "ref_low":  90.0,
            "ref_high": 120.0,
            "source":   "regex",
        })
        results.append({
            "raw_name": "Diastolic BP",
            "value":    float(m.group("diastolic")),
            "unit":     "mmHg",
            "ref_low":  60.0,
            "ref_high": 80.0,
            "source":   "regex",
        })
    return results


def _extract_inline_labeled(line: str) -> Optional[dict]:
    """Fallback: 'TestName: value unit' single-line format."""
    m = _INLINE_LABELED.match(line)
    if not m:
        return None
    try:
        value = float(m.group("value").lstrip("<>"))
    except ValueError:
        return None
    return {
        "raw_name": m.group("name").strip(),
        "value":    value,
        "unit":     (m.group("unit") or "").strip(),
        "ref_low":  None,
        "ref_high": None,
        "source":   "regex",
    }


def _extract_table_row(line: str) -> Optional[dict]:
    """Parse pipe-delimited table rows: | Test Name | 8.2 | % | 4-6 |"""
    parts = [p.strip() for p in _TABLE_SPLIT.split(line) if p.strip()]
    if len(parts) < 2:
        return None
    name_part = parts[0]
    value_part = parts[1] if len(parts) > 1 else ""
    unit_part  = parts[2] if len(parts) > 2 else ""
    range_part = parts[3] if len(parts) > 3 else ""
    try:
        value = float(value_part.lstrip("<>"))
    except ValueError:
        return None
    ref_low, ref_high = _parse_range(range_part)
    return {
        "raw_name": name_part,
        "value":    value,
        "unit":     unit_part,
        "ref_low":  ref_low,
        "ref_high": ref_high,
        "source":   "regex",
    }


def extract_line(line: str) -> list[dict]:
    """Try all extraction strategies on a single line, in priority order.
    
    Returns a list of raw row dicts (may be 0, 1, or 2 for BP lines).
    """
    # Skip section headers and empty lines
    if not line.strip() or line.strip().startswith("##SECTION##"):
        return []

    results = []

    # 1. Blood pressure (special case — generates 2 rows)
    bp = _extract_bp(line)
    if bp:
        results.extend(bp)
        return results  # Don't double-parse the same line

    # 2. Master pattern (most common for Dr Lal format)
    row = _extract_from_master(line)
    if row:
        results.append(row)
        return results

    # 3. Pipe-table format
    row = _extract_table_row(line)
    if row:
        results.append(row)
        return results

    # 4. Inline labeled ("HbA1c: 8.2%")
    row = _extract_inline_labeled(line)
    if row:
        results.append(row)

    # Filter results to ensure they look like actual medical metrics (not 'Age', 'Block-E', etc.)
    final_results = [r for r in results if is_valid_clinical_metric(r["raw_name"])]
    return final_results


# ══════════════════════════════════════════════════════════════════════════════
# 4. LLM FALLBACK — for unresolved lines
# ══════════════════════════════════════════════════════════════════════════════

def _llm_extract_ambiguous_lines(unresolved_lines: list[str]) -> list[dict]:
    """Send unresolved lines to Gemini for structured extraction.
    
    Only called when rule-based extraction fails for a meaningful subset of lines.
    Returns a list of raw row dicts (same schema as rule extraction).
    """
    if not unresolved_lines:
        return []

    import os, json, re as _re
    from utils.gemini_client import call_gemini

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return []

    block = "\n".join(unresolved_lines[:30])  # Cap to avoid token overflow
    prompt = f"""You are a precise medical data extractor.
Below are ambiguous lines from a clinical lab report that our rule-based parser could not parse.

For EACH line, if it contains a lab test value, extract it in this exact JSON format:
{{"name": "test name", "value": 8.2, "unit": "%", "ref_low": 4.0, "ref_high": 6.0}}

If a line is NOT a lab value (e.g., notes, headers, patient info), return null for it.
Return a JSON array with one entry per input line.
If unsure about any field, use null — DO NOT guess or hallucinate.

Lines:
{block}

JSON array:"""

    try:
        data = call_gemini(
            {"contents": [{"parts": [{"text": prompt}]}],
             "generationConfig": {"maxOutputTokens": 1000, "temperature": 0.05}},
            timeout=45,
            caller="[lab_parser/llm_fallback]",
        )
        if not data or "candidates" not in data:
            return []

        raw = data["candidates"][0]["content"]["parts"][0]["text"]
        raw = _re.sub(r"```(?:json)?", "", raw).strip().strip("`").strip()
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return []

        results = []
        for item in parsed:
            if not item or not isinstance(item, dict):
                continue
            try:
                value = float(str(item.get("value", "")).lstrip("<>"))
            except (TypeError, ValueError):
                continue
            results.append({
                "raw_name": str(item.get("name", "")).strip(),
                "value":    value,
                "unit":     str(item.get("unit") or "").strip(),
                "ref_low":  float(item["ref_low"]) if item.get("ref_low") is not None else None,
                "ref_high": float(item["ref_high"]) if item.get("ref_high") is not None else None,
                "source":   "llm",
            })
        return results

    except Exception as e:
        print(f"[lab_parser] LLM fallback failed: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# 5. MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
#  FILTERING & SAFETY
# ══════════════════════════════════════════════════════════════════════════════

INVALID_KEYWORDS = {
    "age", "reported", "block", "sector", "gender", "name", "dr.", 
    "laboratory", "sample", "patient", "mr.", "mrs.", "ms.", "collected",
    "received", "ref. by", "ref by", "id:", "uid:", "phone", "email"
}

def is_valid_clinical_metric(name: str) -> bool:
    """Return False if the name contains administrative noise."""
    lower_name = name.lower()
    # Check if any invalid keyword is a whole word or significant part
    if any(word in lower_name for word in INVALID_KEYWORDS):
        return False
    # Clinical metrics usually have letters, numbers are usually values
    if re.search(r"^\d+$", lower_name): return False # Pure numbers aren't names
    return True

def parse_report(raw_text: str) -> dict:
    """Full parsing pass on a raw medical report.

    Args:
        raw_text: Text extracted from the document (via OCR / pdfplumber).

    Returns:
        {
          "template":       str,          # Detected template ID
          "rows":           list[dict],   # Raw extracted rows (before normalization)
          "unresolved":     list[str],    # Lines that could not be parsed
          "section_labels": list[str],   # All detected section names
        }
    """
    # ── Step A: Detect template ──────────────────────────────────────────────
    template = detect_template(raw_text)
    print(f"[lab_parser] Template detected: {template}")

    # ── Step B: Clean document ───────────────────────────────────────────────
    cleaned = clean_document(raw_text)
    lines = cleaned["cleaned_lines"]
    print(f"[lab_parser] Cleaned lines: {len(lines)}")

    # ── Step C: Parse each line with section tracking ────────────────────────
    rows: list[dict] = []
    unresolved: list[str] = []
    section_labels: list[str] = []
    current_section = "GENERAL"

    for line in lines:
        # Handle section markers inserted by document_cleaner
        if line.startswith("##SECTION##"):
            current_section = line.replace("##SECTION##", "").strip()
            section_labels.append(current_section)
            continue

        extracted = extract_line(line)
        if extracted:
            for row in extracted:
                row["section"] = current_section
                row["source_text"] = line.strip()
            rows.extend(extracted)
        else:
            # Only bother tracking unresolved lines that might contain data
            if _has_potential_data(line):
                unresolved.append(line.strip())

    print(f"[lab_parser] Rule-extracted: {len(rows)} rows, {len(unresolved)} unresolved")

    # ── Step D: LLM fallback for leftovers ──────────────────────────────────
    # Only trigger LLM if we have meaningful lines but failed rule-extraction
    llm_rows = []
    if 0 < len(unresolved) <= 100:
        llm_rows = _llm_extract_ambiguous_lines(unresolved)
        for row in llm_rows:
            row["section"] = "GENERAL"
            row["source_text"] = ""
        rows.extend(llm_rows)
        print(f"[lab_parser] AI fallback recovered: {len(llm_rows)} additional rows")

    return {
        "template":       template,
        "rows":           rows,
        "unresolved":     unresolved,
        "section_labels": list(dict.fromkeys(section_labels)),  # Preserve order
    }


def _has_potential_data(line: str) -> bool:
    """Heuristic: a line worth sending to LLM if it has a digit and is not too long."""
    stripped = line.strip()
    if len(stripped) < 5 or len(stripped) > 200:
        return False
    return bool(re.search(r"\d", stripped))

def parse_report_map_reduce(raw_text: str) -> dict:
    """Map-reduce version of parse_report for large documents.
    1. Chunk text (3000 words, 200 overlap)
    2. Extract labs from each chunk independently
    3. Merge results with deduplication and conflict detection
    """
    from utils.summarizer import chunk_text
    
    words = raw_text.split()
    if len(words) < 4000:
        return parse_report(raw_text)
        
    print(f"[lab_parser] Large document ({len(words)} words). Using map-reduce extraction...")
    chunks = chunk_text(raw_text, chunk_size=3000, overlap=300)
    
    all_chunks_results = []
    all_templates = []
    all_sections = []
    
    for i, chunk in enumerate(chunks):
        print(f"[lab_parser] Processing chunk {i+1}/{len(chunks)}...")
        res = parse_report(chunk)
        all_chunks_results.append(res["rows"])
        all_templates.append(res["template"])
        all_sections.extend(res["section_labels"])
        
    # Merge
    merged_rows, conflicts = merge_lab_results(all_chunks_results)
    
    # Use most frequent template
    from collections import Counter
    template = Counter(all_templates).most_common(1)[0][0] if all_templates else "GENERIC"
    
    return {
        "template":       template,
        "rows":           merged_rows,
        "conflicts":      conflicts,
        "unresolved":     [], # In map-reduce we don't return raw unresolved lines easily
        "section_labels": list(dict.fromkeys(all_sections)),
    }


def merge_lab_results(chunks_rows: list[list[dict]]) -> tuple[list[dict], list[dict]]:
    """Merge rows from multiple chunks. 
    Deduplicates by lab_name.
    If same lab has different values, flags as conflict.
    """
    merged: dict[str, dict] = {}
    conflicts: list[dict] = []
    
    for chunk in chunks_rows:
        for row in chunk:
            name = row["raw_name"].lower().strip()
            val = row["value"]
            
            if name in merged:
                # Check for conflict
                if abs(merged[name]["value"] - val) > 0.001:
                    print(f"[lab_parser] CONFLICT for {name}: {merged[name]['value']} vs {val}")
                    conflicts.append({
                        "metric": name,
                        "values": [merged[name]["value"], val],
                        "source_texts": [merged[name].get("source_text"), row.get("source_text")]
                    })
                # Keep the first one found (or we could keep highest confidence)
                continue
            
            merged[name] = row
            
    return list(merged.values()), conflicts
