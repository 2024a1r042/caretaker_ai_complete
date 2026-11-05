"""Document Cleaner — Phase 1 of the hybrid ingestion pipeline.

Responsibilities:
  1. Remove watermarks and boilerplate text (e.g. "Sample Report")
  2. Deduplicate repeated page headers (Dr Lal multi-page reports)
  3. Normalize whitespace
  4. Skip non-data lines (interpretations, guidelines, doctor notes)
"""
import re
from typing import List


# ─── Skip-Engine Keywords ─────────────────────────────────────────────────────
# These lines contain interpretive or administrative content, NOT lab values.

SKIP_PATTERNS: List[str] = [
    r"interpretation",
    r"guidelines",
    r"reference group",
    r"footnote",
    r"^note[:\s]",
    r"^dear",
    r"^patient:",
    r"^doctor:",
    r"^physician:",
    r"^dr\.",
    r"printed on",
    r"page \d+ of \d+",
    r"sample (report|id|type)",
    r"lab (id|code)",
    r"specimen",
    r"collected",               # "Collected on..." headers
    r"reported (on|by):",
    r"^(approved|reviewed) by",
    r"authorized signatory",
    r"lab director",
    r"accreditation",
    r"this report",
    r"results? should",
    r"consult your",
    r"clinical correlation",
    r"method[:\s]",
    r"^equipment",
    r"^instrument",
    r"barcode",
    r"accession",
    r"^requisition",
    r"^(tel|phone|fax|www|email)[:\s.]",
    r"^address[:\s]",
    r"©",
    r"all rights reserved",
]

_SKIP_RE = re.compile(
    "|".join(SKIP_PATTERNS),
    flags=re.IGNORECASE
)


# ─── Watermark Artifacts ───────────────────────────────────────────────────────

WATERMARK_PHRASES = [
    "Sample Report",
    "Lal PathLabs",             # Keep the name for template detection but not within data lines
    "NABL",
    "ISO 15189",
    "ISO 9001",
]


# ─── Normalisation Helpers ────────────────────────────────────────────────────

def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace into a single space; preserve line breaks."""
    lines = text.split("\n")
    return "\n".join(" ".join(line.split()) for line in lines)


def remove_watermark_artifacts(text: str) -> str:
    """Strip known watermark / lab-name phrases that appear mid-report."""
    for phrase in WATERMARK_PHRASES:
        # Only strip at line-start or line-end where they're noise, not inside a lab-name detection context
        text = re.sub(
            rf"^\s*{re.escape(phrase)}\s*$",
            "",
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    return text


# ─── Deduplication ────────────────────────────────────────────────────────────

def deduplicate_lines(lines: List[str]) -> List[str]:
    """Remove duplicate lines that appear due to repeated page headers.

    Uses a sliding window: a line is considered a duplicate if it appeared
    within the last 80 lines (heuristic for report header size).
    """
    seen: dict[str, int] = {}  # line_text → last_seen_index
    result: List[str] = []
    window = 80

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            result.append(line)
            continue
        last = seen.get(stripped, -1)
        if last == -1 or (idx - last) > window:
            result.append(line)
        seen[stripped] = idx

    return result


# ─── Section Header Detection ─────────────────────────────────────────────────

def is_section_header(line: str) -> bool:
    """Heuristic: ALL-CAPS line with no digits ≥ 5 chars is a section header."""
    stripped = line.strip()
    if len(stripped) < 5:
        return False
    if not stripped.isupper():
        return False
    # Must contain mostly letters (allow '&', ',', '-', spaces)
    letter_count = sum(1 for c in stripped if c.isalpha())
    if letter_count < 4:
        return False
    # Having ANY digit disqualifies it as a pure section header
    if any(c.isdigit() for c in stripped):
        return False
    return True


# ─── Skip-Line Filter ─────────────────────────────────────────────────────────

def should_skip_line(line: str) -> bool:
    """Return True if this line should be excluded from data extraction."""
    stripped = line.strip()
    if not stripped:
        return True
    if len(stripped) < 3:
        return True
    if _SKIP_RE.search(stripped):
        return True
    return False


# ─── Row Reconstruction ───────────────────────────────────────────────────────

def reconstruct_rows(lines: List[str]) -> List[str]:
    """Merge OCR-split rows back into single data lines.

    OCR often splits a single table row across two lines:
        "Creatinine 1.00"
        "mg/dL 0.70 - 1.30"

    Strategy: if a line starts with a unit pattern OR reference-range pattern
    and the previous line has a number, merge them.

    Returns a list of reconstituted data lines.
    """
    _unit_start = re.compile(
        r"^\s*([a-zA-Z%/^]+\s*\d*)\s+[\d.<>]",  # "mg/dL 0.70" or "% 4-6"
        re.IGNORECASE,
    )
    _range_only = re.compile(
        r"^\s*[\d.]+\s*[-–]\s*[\d.]+\s*$"        # "0.70 - 1.30"
    )
    _has_number = re.compile(r"\d")

    merged: List[str] = []
    i = 0
    while i < len(lines):
        current = lines[i].rstrip()
        # Peek at next line
        if i + 1 < len(lines):
            nxt = lines[i + 1].rstrip()
            # Merge condition: current has digit AND next looks like a continuation
            if (
                _has_number.search(current)
                and (_unit_start.match(nxt) or _range_only.match(nxt))
                and not is_section_header(nxt)
            ):
                merged.append(current + "  " + nxt.strip())
                i += 2
                continue
        merged.append(current)
        i += 1

    return merged


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def clean_document(raw_text: str) -> dict:
    """Full cleaning pass on extracted OCR text.

    Returns:
        {
          "cleaned_lines": List[str],   # filtered, deduped, mergeable lines
          "raw_clean": str,             # joined cleaned text for downstream use
          "section_map": dict           # {line_index: section_name}
        }
    """
    if not raw_text:
        return {"cleaned_lines": [], "raw_clean": "", "section_map": {}}

    # Step 1: Remove watermarks and normalize whitespace
    text = remove_watermark_artifacts(raw_text)
    text = normalize_whitespace(text)

    # Step 2: Split into lines
    lines = text.split("\n")

    # Step 3: Deduplicate repeated page headers
    lines = deduplicate_lines(lines)

    # Step 4: Filter skip lines, but note section headers separately
    section_map: dict[int, str] = {}
    cleaned: List[str] = []

    current_section = "GENERAL"
    for raw_line in lines:
        line = raw_line.strip()

        if is_section_header(line):
            current_section = line
            # Keep section headers in cleaned but mark them
            cleaned.append(f"##SECTION## {line}")
            section_map[len(cleaned) - 1] = line
            continue

        if should_skip_line(line):
            continue

        cleaned.append(line)

    # Step 5: Reconstruct OCR-split rows
    cleaned = reconstruct_rows(cleaned)

    return {
        "cleaned_lines": cleaned,
        "raw_clean": "\n".join(cleaned),
        "section_map": section_map,
    }
