"""Special instructions/notes extraction engine.

Extracts order notes, remarks, special handling instructions, warnings from documents.

Patterns recognized:
- "notes:", "remarques:", "instructions:", "attention:"
- "⚠️", "❌", "✓"
- "NB:", "P.S.:", "IMPORTANT"
- Warnings: "fragile", "ne pas plier", "haut", "bas"
"""

import re
from typing import Optional


def _extract_note_section(text: str) -> Optional[str]:
    """Extract text from note/remark sections.
    
    Looks for patterns like:
    - notes: [content]
    - remarques: [content]
    - instructions: [content]
    """
    if not text:
        return None
    
    # Pattern: keyword followed by colon and content
    patterns = [
        r"(?:notes|remarques|instructions|attention|special)\s*:?\s*([^\\n]{5,200})",
        r"(?:NB|P\.S\.)\s*:?\s*([^\\n]{5,200})",
        r"(?:IMPORTANT|WARNING|AVERTISSEMENT)\s*:?\s*([^\\n]{5,200})",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            content = match.group(1).strip()
            if 5 <= len(content) <= 200:
                return content
    
    return None


def _extract_handling_instructions(text: str) -> Optional[str]:
    """Extract handling/shipping instructions.
    
    Patterns:
    - "fragile", "ne pas plier", "haut/bas", "côté"
    - "attention", "caution", "handle with care"
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Build instructions from detected keywords
    instructions = []
    
    if re.search(r"\b(?:fragile|casse|cassable)\b", text_lower):
        instructions.append("FRAGILE")
    
    if re.search(r"(?:ne\s+pas\s+)?plier", text_lower):
        instructions.append("NE PAS PLIER")
    
    if re.search(r"(?:haut|top|up)\b", text_lower):
        instructions.append("HAUT")
    
    if re.search(r"(?:bas|bottom|down)\b", text_lower):
        instructions.append("BAS")
    
    if re.search(r"(?:côté|side|edge)\b", text_lower):
        instructions.append("CÔTÉ")
    
    if re.search(r"(?:attention|caution|handle\s+with\s+care)\b", text_lower):
        instructions.append("À MANIPULER AVEC SOIN")
    
    if instructions:
        return " | ".join(instructions)
    
    return None


def _extract_delivery_instructions(text: str) -> Optional[str]:
    """Extract delivery/contact instructions.
    
    Patterns:
    - "contacter", "appeler", "email", "téléphoner"
    - "avant livraison", "à réception"
    - "rendez-vous"
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    patterns = [
        r"(?:contacter|appeler|téléphoner|email)\s+([^\\n]{5,100})",
        r"(?:avant\s+livraison|à\s+réception)\s*:?\s*([^\\n]{5,100})",
        r"(?:rendez-vous|appointment)\s*:?\s*([^\\n]{5,100})",
        r"(?:livrer\s+à|deliver\s+to)\s*:?\s*([^\\n]{5,100})",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_lower, re.MULTILINE)
        if match:
            content = match.group(1).strip()
            if 5 <= len(content) <= 100:
                return content
    
    return None


def extract_special_instructions(text: str) -> Optional[str]:
    """Extract special instructions from text.
    
    Returns combined instructions or None if none found.
    Strategy:
    1. Look for explicit note sections
    2. Look for handling instructions
    3. Look for delivery instructions
    4. Combine if multiple found
    """
    if not text or not isinstance(text, str):
        return None
    
    instructions = []
    
    # Try to extract each type
    notes = _extract_note_section(text)
    if notes:
        instructions.append(notes)
    
    handling = _extract_handling_instructions(text)
    if handling:
        instructions.append(handling)
    
    delivery = _extract_delivery_instructions(text)
    if delivery:
        instructions.append(delivery)
    
    if instructions:
        # Combine and limit total length
        combined = " | ".join(instructions)
        if len(combined) > 500:
            combined = combined[:497] + "..."
        return combined
    
    return None


def extract_warnings(text: str) -> Optional[str]:
    """Extract warnings/cautions from text.
    
    Looks for keywords: ⚠️, WARNING, URGENT, IMPORTANT, ATTENTION
    """
    if not text or not isinstance(text, str):
        return None
    
    text_upper = text.upper()
    
    warnings = []
    
    if "⚠️" in text:
        warnings.append("⚠️")
    
    if re.search(r"\b(WARNING|AVERTISSEMENT)\b", text_upper):
        warnings.append("WARNING")
    
    if re.search(r"\b(URGENT|IMMÉDIAT)\b", text_upper):
        warnings.append("URGENT")
    
    if re.search(r"\b(IMPORTANT|CRITIQUE)\b", text_upper):
        warnings.append("IMPORTANT")
    
    if re.search(r"\b(ATTENTION|CAUTION)\b", text_upper):
        warnings.append("ATTENTION")
    
    if warnings:
        return " | ".join(warnings)
    
    return None
