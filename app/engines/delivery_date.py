"""Delivery date extraction engine.

Extracts delivery date/urgency from order documents using pattern matching.
Falls back to today's date when the raw text is present but unrecognizable.

Patterns recognized:
- Date formats: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY (4-digit year)
- Short-year formats: DD/MM/YY, DD.MM.YY (2-digit year → 2000+)
- Week/year formats: SS/AA, SSAA (e.g. 47/24, 4824)
- Week labels: "semaine N", "sem N", "S N", "wk N"
- Urgency keywords: URGENT, EXPRESS, NORMAL, STANDARD
- Delay: X jours, X days
- Fallback: today's date when raw text is present but unparseable
"""

import re
from datetime import date, datetime, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_date_formats(text: str) -> Optional[str]:
    """Parse common date formats to ISO YYYY-MM-DD.

    Handles:
    - DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY  (4-digit year)
    - DD/MM/YY, DD.MM.YY  (2-digit year → 20YY)
    """
    if not text:
        return None

    # 4-digit year: DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", text)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            if 1 <= day <= 31 and 1 <= month <= 12 and year >= 2020:
                return f"{year:04d}-{month:02d}-{day:02d}"
        except (ValueError, TypeError):
            pass

    # 2-digit year: DD/MM/YY or DD.MM.YY (no dash to avoid clashing with ISO)
    m = re.search(r"(\d{1,2})[/.](\d{1,2})[/.](\d{2})(?!\d)", text)
    if m:
        day, month, year_2d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = 2000 + year_2d
        try:
            if 1 <= day <= 31 and 1 <= month <= 12:
                return f"{year:04d}-{month:02d}-{day:02d}"
        except (ValueError, TypeError):
            pass

    return None


def _parse_week_year(text: str) -> Optional[str]:
    """Parse week/year formats to ISO YYYY-MM-DD (Monday of that week).

    Handles:
    - SS/AA  (e.g. 47/24  → week 47 of 2024)
    - SSAA   (e.g. 4824   → week 48 of 2024)
    - "semaine N" / "sem N" / "S N" / "wk N"
    """
    if not text:
        return None
    folded = text.strip().lower()

    # "semaine 13", "sem 13", "S13", "wk 13"
    m = re.search(r"(?:semaine|sem\.?|wk\.?|s)\s*(\d{1,2})\b", folded)
    if m:
        week = int(m.group(1))
        if 1 <= week <= 53:
            # Use current year; if week is already past, use next year
            today = date.today()
            try:
                candidate = datetime.strptime(f"{today.year}-W{week:02d}-1", "%Y-W%W-%w").date()
                if candidate < today:
                    candidate = datetime.strptime(f"{today.year + 1}-W{week:02d}-1", "%Y-W%W-%w").date()
                return candidate.isoformat()
            except ValueError:
                pass

    # SS/AA (week/2-digit-year): e.g. "47/24"
    m = re.fullmatch(r"(\d{1,2})/(\d{2})", text.strip())
    if m:
        week, year_2d = int(m.group(1)), int(m.group(2))
        if 1 <= week <= 53:
            year = 2000 + year_2d
            try:
                return datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w").date().isoformat()
            except ValueError:
                pass

    # SSAA compact (4-digit: first 2 = week, last 2 = year): e.g. "4824"
    m = re.fullmatch(r"(\d{2})(\d{2})", text.strip())
    if m:
        week, year_2d = int(m.group(1)), int(m.group(2))
        if 1 <= week <= 53 and year_2d >= 24:
            year = 2000 + year_2d
            try:
                return datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w").date().isoformat()
            except ValueError:
                pass

    return None


def _extract_urgency(text: str) -> Optional[str]:
    """Extract urgency level from text.

    Returns: URGENT, EXPRESS, NORMAL, STANDARD, or None
    """
    if not text:
        return None

    text_upper = text.upper()

    if re.search(r"\b(URGENT|EXTRÊMEMENT|IMMÉDIAT|ASAP)\b", text_upper):
        return "URGENT"
    if re.search(r"\b(EXPRESS|RAPIDE|PRIORITAIRE|PRIORITY)\b", text_upper):
        return "EXPRESS"
    if re.search(r"\b(NORMAL|STANDARD|COURANT|REGULAR)\b", text_upper):
        return "NORMAL"

    return None


def _extract_delivery_delay(text: str) -> Optional[str]:
    """Extract delivery delay (e.g. 'dans X jours') and return ISO date."""
    if not text:
        return None

    m = re.search(r"(?:dans|délai)\s+(\d+)\s+(?:jours|days|j\b)", text.lower())
    if m:
        try:
            days = int(m.group(1))
            if 0 < days <= 365:
                return (date.today() + timedelta(days=days)).isoformat()
        except (ValueError, TypeError):
            pass
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_delivery_date(text: str) -> Optional[str]:
    """Extract delivery date from raw text.

    Returns ISO YYYY-MM-DD or None when text is empty/None.
    When text is present but unparseable, returns None (caller should
    use normalize_delivery_date_with_fallback for a today-fallback).
    """
    if not text or not isinstance(text, str):
        return None

    date_result = _parse_date_formats(text)
    if date_result:
        return date_result

    week_result = _parse_week_year(text)
    if week_result:
        return week_result

    delay_result = _extract_delivery_delay(text)
    if delay_result:
        return delay_result

    return None


def normalize_delivery_date_with_fallback(text: str | None) -> str:
    """Return ISO delivery date, falling back to today when text is absent or unparseable.

    Use this instead of extract_delivery_date() at ingestion time so that
    unparseable raw values (Au plus tôt, DEBUT MARS, semaine 13, etc.) never
    create DELIVERY_DATE_INVALID anomalies — the ADV sees today's date, which
    is always a valid lower bound.
    """
    if text:
        parsed = extract_delivery_date(text.strip())
        if parsed:
            return parsed
    return date.today().isoformat()


def extract_delivery_urgency(text: str) -> Optional[str]:
    """Extract delivery urgency level.

    Returns: URGENT, EXPRESS, NORMAL, STANDARD, or None
    """
    if not text or not isinstance(text, str):
        return None
    return _extract_urgency(text)


def extract_delivery_info(text: str) -> dict:
    """Extract complete delivery information.

    Returns dict with:
    - delivery_date: ISO format date or None
    - urgency: URGENT/EXPRESS/NORMAL/STANDARD or None
    """
    if not text or not isinstance(text, str):
        return {"delivery_date": None, "urgency": None}

    return {
        "delivery_date": extract_delivery_date(text),
        "urgency": extract_delivery_urgency(text),
    }
