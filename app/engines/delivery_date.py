"""Delivery date extraction engine.

Extracts delivery date/urgency from order documents using pattern matching.
Falls back to LLM for complex cases.

Patterns recognized:
- Date formats: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY
- Urgency keywords: URGENT, EXPRESS, NORMAL, STANDARD
- Delay: X jours, X days
"""

import re
from datetime import datetime, timedelta
from typing import Optional


def _parse_date_formats(text: str) -> Optional[str]:
    """Try to parse common date formats.
    
    Supports:
    - 31/12/2024
    - 31-12-2024
    - 31.12.2024
    """
    if not text:
        return None
    
    # Pattern 1: DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
    date_pattern = r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})"
    match = re.search(date_pattern, text)
    
    if match:
        day, month, year = match.groups()
        try:
            day, month, year = int(day), int(month), int(year)
            if 1 <= day <= 31 and 1 <= month <= 12 and year >= 2024:
                # Return as ISO format: YYYY-MM-DD
                return f"{year:04d}-{month:02d}-{day:02d}"
        except (ValueError, TypeError):
            pass
    
    return None


def _extract_urgency(text: str) -> Optional[str]:
    """Extract urgency level from text.
    
    Returns: URGENT, EXPRESS, NORMAL, STANDARD, or None
    """
    if not text:
        return None
    
    text_upper = text.upper()
    
    # High priority
    if re.search(r"\b(URGENT|EXTRÊMEMENT|IMMÉDIAT|ASAP|ASAP)\b", text_upper):
        return "URGENT"
    
    # Medium priority
    if re.search(r"\b(EXPRESS|RAPIDE|PRIORITAIRE|PRIORITY)\b", text_upper):
        return "EXPRESS"
    
    # Standard
    if re.search(r"\b(NORMAL|STANDARD|COURANT|REGULAR)\b", text_upper):
        return "NORMAL"
    
    return None


def _extract_delivery_delay(text: str) -> Optional[str]:
    """Extract delivery delay from text.
    
    Patterns:
    - "dans X jours", "X days", "délai X jours"
    - "livraison X jours"
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Pattern: "dans X jours" or "X jours"
    delay_pattern = r"(?:dans|délai)\s+(\d+)\s+(?:jours|days|j\b)"
    match = re.search(delay_pattern, text_lower)
    
    if match:
        try:
            days = int(match.group(1))
            if 0 < days <= 365:
                delivery_date = datetime.now() + timedelta(days=days)
                return delivery_date.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass
    
    return None


def extract_delivery_date(text: str) -> Optional[str]:
    """Extract delivery date from order text.
    
    Strategy:
    1. Look for explicit date patterns (DD/MM/YYYY)
    2. Look for delay patterns (X jours)
    3. Return None if no date found
    
    Returns date in ISO format: YYYY-MM-DD or None
    """
    if not text or not isinstance(text, str):
        return None
    
    # Try explicit date first
    date_result = _parse_date_formats(text)
    if date_result:
        return date_result
    
    # Try delay calculation
    delay_result = _extract_delivery_delay(text)
    if delay_result:
        return delay_result
    
    return None


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
