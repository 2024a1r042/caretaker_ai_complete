"""Date Extractor — Deterministic regex-based date extraction.

Priority order (highest → lowest confidence):
  1. Near "Report Date:" / "Reported:" / "Collection Date:" label
  2. Header section (first 20 lines of document)
  3. Any date found in the body
  4. Fallback: None (caller uses upload date)

Supports formats common in Indian diagnostic labs:
  - DD/MM/YYYY       (17/01/2024)
  - DD-MM-YYYY       (17-01-2024)
  - D MMM YYYY       (17 Jan 2024)
  - DD MMM YYYY      (17 Jan 2024)
  - D MMMM YYYY      (17 January 2024)
  - YYYY-MM-DD       (2024-01-17)
"""
import re
from datetime import date, datetime
from typing import Optional, List

# ─── Month Maps ───────────────────────────────────────────────────────────────

_MONTHS_SHORT = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTHS_FULL = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}
_ALL_MONTHS = {**_MONTHS_SHORT, **_MONTHS_FULL}


# ─── Regex Patterns ───────────────────────────────────────────────────────────

# Labeled date: "Report Date: 17 Jan 2024" | "Reported: 17/01/2024"
_LABELED_PATTERNS = [
    # "Report Date: DD MMM YYYY" or "DD/MM/YYYY"
    re.compile(
        r"(?:report\s+date|reported(?:\s+on)?|collection\s+date|"
        r"date\s+of\s+report|date\s+of\s+collection|visit\s+date|"
        r"sample\s+date|registration\s+date)"
        r"\s*[:\-]?\s*"
        r"(\d{1,2}[\s/\-](?:\d{1,2}|[a-z]+)[\s/\-]\d{2,4})",
        re.IGNORECASE,
    ),
    # ISO after a label
    re.compile(
        r"(?:report\s+date|reported|collection\s+date)"
        r"\s*[:\-]?\s*"
        r"(\d{4}-\d{2}-\d{2})",
        re.IGNORECASE,
    ),
]

# Bare date patterns (no label context)
_BARE_PATTERNS = [
    re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b"),            # DD/MM/YYYY
    re.compile(r"\b(\d{1,2}-\d{1,2}-\d{4})\b"),            # DD-MM-YYYY
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),                # ISO YYYY-MM-DD
    re.compile(
        r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
        r"|January|February|March|April|June|July|August|September|October|"
        r"November|December)\s+\d{4})\b",
        re.IGNORECASE,
    ),
]


# ─── Parsing Helpers ──────────────────────────────────────────────────────────

def _try_parse(text: str) -> Optional[date]:
    """Attempt to parse a date string into a Python date object."""
    text = text.strip()
    # ISO format
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        pass
    # DD/MM/YYYY or DD-MM-YYYY
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    # Word month formats: "17 Jan 2024", "17 January 2024"
    m = re.match(
        r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", text, re.IGNORECASE
    )
    if m:
        day, month_str, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        month = _ALL_MONTHS.get(month_str)
        if month:
            try:
                return date(year, month, day)
            except ValueError:
                pass
    return None


def _is_plausible(d: date) -> bool:
    """Filter out obviously wrong dates (too old / in the future)."""
    today = date.today()
    return date(2000, 1, 1) <= d <= today


# ─── Main Extraction Function ─────────────────────────────────────────────────

def extract_date_from_text(text: str, fallback: Optional[date] = None) -> Optional[date]:
    """Extract the most likely report date from document text.

    Args:
        text: Raw or cleaned document text.
        fallback: Date to return if no date found (usually the upload date).

    Returns:
        The extracted date, or fallback if nothing found.
    """
    if not text:
        return fallback

    lines = text.split("\n")

    # ── Priority 1: Search near labeled keywords ──────────────────────────────
    for line in lines:
        for pattern in _LABELED_PATTERNS:
            m = pattern.search(line)
            if m:
                parsed = _try_parse(m.group(1))
                if parsed and _is_plausible(parsed):
                    return parsed

    # ── Priority 2: Search header (first 25 lines) ───────────────────────────
    header_text = "\n".join(lines[:25])
    for pattern in _BARE_PATTERNS:
        for m in pattern.finditer(header_text):
            parsed = _try_parse(m.group(1))
            if parsed and _is_plausible(parsed):
                return parsed

    # ── Priority 3: Search full body for any plausible date ──────────────────
    candidates: List[date] = []
    for pattern in _BARE_PATTERNS:
        for m in pattern.finditer(text):
            parsed = _try_parse(m.group(1))
            if parsed and _is_plausible(parsed):
                candidates.append(parsed)

    if candidates:
        # Return the most recent (likely the actual report date)
        return max(candidates)

    # ── Priority 4: Return fallback ───────────────────────────────────────────
    return fallback
