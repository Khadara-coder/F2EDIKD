"""Memo system: LLM-maintained knowledge base for edge cases.

The memo is a .md file that stores learned patterns, client-specific rules,
and resolution history. It is:
- READ by the pipeline as additional context for LLM fallback
- UPDATED after manual validations or new edge case detection
- VERSIONED via git (human-readable audit trail)
"""
from pathlib import Path
from typing import Optional
import re

_MEMO_PATH = Path(__file__).parent.parent / "data" / "memo_resolutions.md"


def get_memo() -> str:
    """Read the full memo content."""
    if _MEMO_PATH.exists():
        return _MEMO_PATH.read_text(encoding="utf-8")
    return ""


def get_memo_section(section_keyword: str) -> str:
    """Extract a specific section from the memo by keyword."""
    memo = get_memo()
    if not memo:
        return ""
    
    lines = memo.split("\n")
    result = []
    in_section = False
    
    for line in lines:
        if line.startswith("## ") and section_keyword.lower() in line.lower():
            in_section = True
            result.append(line)
        elif line.startswith("## ") and in_section:
            break  # Next section
        elif in_section:
            result.append(line)
    
    return "\n".join(result)


def search_memo(query: str) -> str:
    """Search memo for lines matching a query (case-insensitive)."""
    memo = get_memo()
    if not memo:
        return ""
    
    query_lower = query.lower()
    matching_lines = []
    lines = memo.split("\n")
    
    for i, line in enumerate(lines):
        if query_lower in line.lower():
            # Include context (2 lines before, 2 after)
            start = max(0, i - 2)
            end = min(len(lines), i + 3)
            context = lines[start:end]
            matching_lines.append("\n".join(context))
    
    return "\n---\n".join(matching_lines[:5])  # Max 5 matches


def get_client_memo(client_name: str) -> str:
    """Get all memo entries related to a client name."""
    return search_memo(client_name)


def update_memo(new_entry: str, section: str = "Cas detectes automatiquement") -> bool:
    """Append a new entry to the memo under the specified section.
    
    Args:
        new_entry: The text to add (markdown formatted)
        section: Which section to add it under
    
    Returns:
        True if updated successfully
    """
    try:
        memo = get_memo()
        
        # Find the section or create it
        section_header = f"## {section}"
        if section_header in memo:
            # Append after section header
            idx = memo.find(section_header)
            # Find end of section (next ## or end)
            next_section = memo.find("\n## ", idx + len(section_header))
            if next_section == -1:
                # Append at end
                memo = memo.rstrip() + "\n\n" + new_entry + "\n"
            else:
                # Insert before next section
                memo = memo[:next_section] + "\n" + new_entry + "\n" + memo[next_section:]
        else:
            # Add new section at end
            memo = memo.rstrip() + "\n\n---\n\n" + section_header + "\n\n" + new_entry + "\n"
        
        # Update the "Dernière MAJ" line
        import datetime
        today = datetime.date.today().isoformat()
        memo = re.sub(
            r"Dernière MAJ: [\d-]+",
            f"Dernière MAJ: {today}",
            memo
        )
        
        _MEMO_PATH.write_text(memo, encoding="utf-8")
        return True
    except Exception:
        return False


def build_memo_context_for_llm(text: str, soldto: str = "", client_name: str = "") -> str:
    """Build a compact memo context string to inject into LLM prompts.
    
    Searches the memo for relevant entries based on:
    - Client name
    - SOLDTO
    - Any postal codes found in the text
    
    Returns a string suitable for injection into LLM prompts (max ~1000 chars).
    """
    relevant_parts = []
    
    # Search by client name
    if client_name:
        # Clean name (remove leading dots)
        clean_name = client_name.lstrip(".").split("(")[0].strip()
        if clean_name and len(clean_name) > 3:
            found = search_memo(clean_name)
            if found:
                relevant_parts.append(found)
    
    # Search by SOLDTO
    if soldto:
        found = search_memo(soldto)
        if found:
            relevant_parts.append(found)
    
    # Search by postal codes in text
    postals = re.findall(r"\b(\d{5})\b", text[:3000])
    for postal in postals[:3]:  # Max 3 postals
        found = search_memo(postal)
        if found and found not in relevant_parts:
            relevant_parts.append(found)
            break  # One postal match is enough
    
    if not relevant_parts:
        return ""
    
    context = "\n".join(relevant_parts)
    # Truncate to ~1500 chars max
    if len(context) > 1500:
        context = context[:1500] + "\n[...]"
    
    return f"\n--- MEMO (cas connus) ---\n{context}\n--- FIN MEMO ---\n"
