from __future__ import annotations

import re

from app.text_utils import compact_text, fold_text, unique


def enrich_line_items_with_materials(rows: list[dict], materials_by_id: dict[str, str]) -> list[dict]:
    if not materials_by_id:
        return rows
    for row in rows:
        article = re.sub(r"\s+", "", row.get("article", ""))
        description = materials_by_id.get(article)
        if description:
            row["designation_masterdata"] = description
    return rows


def _amount_pattern() -> str:
    return r"(?:(?:\d{1,3}(?:[ .]\d{3})*|\d+)[,.]\d{2}\s?(?:€|EUR|E|euros?)?)"


def _normalize_article_token(token: str) -> str:
    token = (token or "").strip().upper()
    token = re.sub(r"\s+", "", token)
    token = re.sub(r"^(ELM|EL)", "", token)
    return token


def _extract_customer_reference(text: str) -> str:
    """Extract customer/order reference from text.
    
    Patterns:
    - ref client/commande/po
    - votre référence
    - order ref/number
    """
    if not text:
        return ""
    text_folded = fold_text(text)
    
    # Pattern 1: "ref" followed by value
    patterns = [
        r"(?:réf|ref|reference|po)\s+(?:client|commande)?\s*:?\s*([A-Z0-9\-]{3,20})",
        r"(?:votre\s+)?référence\s*:?\s*([A-Z0-9\-]{3,20})",
        r"(?:order|commande)\s+(?:ref|number|ref\.)\s*:?\s*([A-Z0-9\-]{3,20})",
        r"^([A-Z0-9]{3,20})\s*$",  # Standalone code at line start
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_folded, re.IGNORECASE | re.MULTILINE)
        if match:
            ref = match.group(1).strip()
            if 3 <= len(ref) <= 20 and re.match(r"[A-Z0-9\-]+", ref, re.IGNORECASE):
                return ref.upper()
    return ""


def _extract_payment_terms(text: str) -> str:
    """Extract payment terms from text.
    
    Patterns:
    - NET 30/60/90 days
    - Payment terms: ...
    - Conditions paiement
    - COMPTANT, VIREMENT, CHÈQUE
    """
    if not text:
        return ""
    text_folded = fold_text(text)
    
    # Standard payment terms patterns
    patterns = [
        r"(?:conditions\s+)?paiement\s*:?\s*(NET\s+\d+[Jj]?|NET|COMPTANT|VIREMENT|CHÈQUE|CRÉDIT)",
        r"\b(NET\s+(?:\d+[Jj])?(?:\s+jours)?|COMPTANT|VIREMENT|CHÈQUE|CRÉDIT)\b",
        r"(?:payment\s+terms?|net|payable)\s*:?\s*(NET\s+\d+|COMPTANT|VIREMENT)",
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text_folded, re.IGNORECASE)
        if match:
            term = match.group(1).strip().upper()
            if term and len(term) <= 30:
                return term
    return ""


def _normalize_article_token(token: str) -> str:
    token = (token or "").strip().upper()
    token = re.sub(r"\s+", "", token)
    token = re.sub(r"^(ELM|EL)", "", token)
    return token


def _extract_amount_tokens(text: str) -> list[str]:
    return [compact_text(m.group(0)) for m in re.finditer(_amount_pattern(), text, flags=re.IGNORECASE)]


def _extract_article_tail_values(window_text: str, article: str) -> tuple[str, str, str]:
    text = compact_text(window_text).replace("|", " ")
    text = re.sub(r"\s+", " ", text).strip()
    parts = text.split(article, 1)
    if len(parts) != 2:
        return "", "", ""
    tail = parts[1]
    amount = _amount_pattern()
    pattern_with_u = re.match(
        rf"^\s*(?P<qty>\d{{1,4}}(?:[.,]\d{{1,3}})?)\s+"
        rf"(?P<amount>{amount})\s+\S+\s+U\s+"
        rf"(?P<unit_price>{amount})",
        tail,
        flags=re.IGNORECASE,
    )
    if pattern_with_u:
        return (
            compact_text(pattern_with_u.group("qty")),
            compact_text(pattern_with_u.group("unit_price")),
            compact_text(pattern_with_u.group("amount")),
        )

    pattern_simple = re.match(
        rf"^\s*(?P<qty>\d{{1,4}}(?:[.,]\d{{1,3}})?)\s+"
        rf"(?P<amount>{amount})\s+"
        rf"(?P<unit_price>{amount})",
        tail,
        flags=re.IGNORECASE,
    )
    if pattern_simple:
        return (
            compact_text(pattern_simple.group("qty")),
            compact_text(pattern_simple.group("unit_price")),
            compact_text(pattern_simple.group("amount")),
        )
    return "", "", ""


def _is_unit_token(value: str) -> bool:
    return bool(re.fullmatch(r"PCE|PIECE|PCS|PC|UN|EA|PI|P", compact_text(value), flags=re.IGNORECASE))


def _to_natural_qty_str(value: str) -> str:
    """Convert an extracted quantity string to a natural integer string.
    
    Business rule: quantities are always exact natural integers >= 1.
    No rounding tolerance: only exact integers are accepted.
    Returns "" if value is not an exact positive integer.
    """
    if not value:
        return ""
    try:
        v = float(value.replace(",", ".").replace(" ", ""))
    except (ValueError, TypeError):
        return ""
    if v <= 0:
        return ""
    rounded = round(v)
    if rounded < 1:
        return ""
    # Require exact integer — no rounding tolerance
    if v == float(rounded):
        return str(rounded)
    return ""  # Non-integer — reject


def _extract_table_quantity_and_unit(cells: list[str], article_idx: int, amount_indexes: list[int]) -> tuple[str, str]:
    first_amount_idx = amount_indexes[0] if amount_indexes else len(cells)
    numeric_indexes = [
        idx
        for idx, cell in enumerate(cells)
        if idx != article_idx
        and idx < first_amount_idx
        and re.fullmatch(r"\d+(?:[,.]\d+)?", cell)
    ]
    if not numeric_indexes:
        return "", ""

    preferred_idx = numeric_indexes[-1]
    unit = ""
    if preferred_idx + 1 < len(cells) and _is_unit_token(cells[preferred_idx + 1]):
        unit = compact_text(cells[preferred_idx + 1]).upper().replace("PIECE", "PCE")
    elif preferred_idx - 1 >= 0 and _is_unit_token(cells[preferred_idx - 1]):
        unit = compact_text(cells[preferred_idx - 1]).upper().replace("PIECE", "PCE")
    return compact_text(cells[preferred_idx]), unit


def extract_line_items_from_multiline_lines(lines: list[str]) -> list[dict]:
    """Extract rows when OCR split table data across adjacent lines.

    Typical patterns:
    - line N: article id
      line N+1: PIECE 20,000 275,00
      line N+2: 275,00 5500,00
    - line N: PIECE 66,000 1583,18400
      line N+1: 87382000520
    """
    rows: list[dict] = []
    seen: set[str] = set()

    article_re = re.compile(r"\b(?P<art>(?:ELM|EL)?\d{7,11})\b", flags=re.IGNORECASE)
    qty_unit_re = re.compile(
        r"(?P<qty>\d{1,4}(?:[,.]\d{1,3})?)\s*(?P<unit>PCE|PIECE|PCS|PC|UN|EA|QTÉ|QTE|QTY|QNT)\b"
        r"|\b(?P<unit2>PCE|PIECE|PCS|PC|UN|EA|QTÉ|QTE|QTY|QNT)\b\s*(?P<qty2>\d{1,4}(?:[,.]\d{1,3})?)",
        flags=re.IGNORECASE,
    )

    for idx, raw in enumerate(lines):
        line = compact_text(raw)
        if not line:
            continue

        article = ""
        m_art = article_re.search(line)
        anchor_idx = idx

        if m_art:
            article = _normalize_article_token(m_art.group("art"))
        else:
            # Pattern with unit/qty first and article on next line.
            if qty_unit_re.search(line) and idx + 1 < len(lines):
                nxt = compact_text(lines[idx + 1])
                m_next_art = article_re.search(nxt)
                if m_next_art:
                    article = _normalize_article_token(m_next_art.group("art"))
                    anchor_idx = idx + 1

        if not article or not re.fullmatch(r"\d{7,11}", article):
            continue
        if article in seen:
            continue

        win_start = max(0, anchor_idx - 1)
        win_end = min(len(lines), anchor_idx + 8)
        window_lines = [compact_text(x) for x in lines[win_start:win_end] if compact_text(x)]
        window_text = " | ".join(window_lines)

        qty = ""
        unit = ""
        for wl in window_lines:
            qm = qty_unit_re.search(wl)
            if not qm:
                continue
            qty = (qm.group("qty") or qm.group("qty2") or "").strip()
            unit = (qm.group("unit") or qm.group("unit2") or "").upper().replace("PIECE", "PCE")
            if qty:
                break

        amounts = _extract_amount_tokens(window_text)
        unit_price = ""
        amount = ""
        if amounts:
            if len(amounts) == 1:
                unit_price = amounts[0]
            else:
                unit_price = amounts[0]
                amount = amounts[-1]

        if not qty or (unit_price and amount and unit_price == amount):
            tail_qty, tail_unit_price, tail_amount = _extract_article_tail_values(window_text, article)
            if tail_qty:
                qty = tail_qty
            if tail_unit_price:
                unit_price = tail_unit_price
            if tail_amount:
                amount = tail_amount

        # Pull a short designation text around article, excluding strong numeric lines.
        designation = ""
        if idx > 0:
            prev = compact_text(lines[idx - 1])
            if prev and not re.search(r"\d{5,}|\bPCE\b|\bPIECE\b|\bPCS\b", prev, re.I):
                designation = prev
        if not designation and idx + 1 < len(lines):
            nxt = compact_text(lines[idx + 1])
            if nxt and not re.search(r"\d{5,}|\bPCE\b|\bPIECE\b|\bPCS\b", nxt, re.I):
                designation = nxt

        if not qty and not unit_price and not amount:
            continue

        seen.add(article)
        rows.append(
            {
                "designation": designation,
                "article": article,
                "delivery_date": "",
                "quantity": _to_natural_qty_str(qty),
                "unit": unit,
                "unit_price": unit_price,
                "amount": amount,
                "customer_reference": "",
                "payment_terms": "",
                "parser": "multiline_window",
            }
        )

    return rows


def extract_line_items_from_lines(lines: list[str]) -> list[dict]:
    rows = []
    header_index = None
    for index, line in enumerate(lines):
        folded = fold_text(line)
        if "article" in folded and ("designation" in folded or "design" in folded):
            header_index = index
            break

    if header_index is None:
        # No obvious header: still try strict row-level extraction.
        header_index = -1

    amount = _amount_pattern()
    for line in lines[header_index + 1 :]:
        folded = fold_text(line)
        if any(stop in folded for stop in ("total ht", "total ttc", "net a payer", "frais de port", "conditions")):
            break
        if not compact_text(line):
            continue

        cells = [compact_text(cell) for cell in re.split(r"\s{2,}|\t|\|", line) if compact_text(cell)]
        if len(cells) >= 5:
            article_idx = next((idx for idx, cell in enumerate(cells) if re.fullmatch(r"[A-Z]{0,4}\d{5,}|\d{5,}", cell, flags=re.I)), None)
            if article_idx is not None:
                article = cells[article_idx]
                amount_indexes = [idx for idx, cell in enumerate(cells) if re.search(r"\d[,.]\d{2}", cell)]
                amounts = [cells[idx] for idx in amount_indexes]
                quantity, unit = _extract_table_quantity_and_unit(cells, article_idx, amount_indexes)
                designation_cells = [
                    cell
                    for idx, cell in enumerate(cells)
                    if idx != article_idx and not re.fullmatch(r"\d+(?:[,.]\d+)?", cell) and not re.search(r"\d[,.]\d{2}", cell)
                    and not _is_unit_token(cell)
                ]
                row = {
                    "designation": compact_text(" ".join(designation_cells)),
                    "article": article,
                    "delivery_date": next((cell for cell in cells if re.fullmatch(r"\d{2}/\d{2}/\d{4}", cell)), ""),
                    "quantity": _to_natural_qty_str(quantity),
                    "unit": unit,
                    "unit_price": amounts[0] if amounts else "",
                    "amount": amounts[-1] if amounts else "",
                    "customer_reference": "",
                    "payment_terms": "",
                    "parser": "table_lines",
                }
                if row["article"]:
                    rows.append(row)
                continue

        match = re.search(
            rf"(?P<article>[A-Z]{{0,4}}\d{{5,}}|\d{{5,}})\s+"
            r"(?P<designation>.+?)\s+"
            r"(?P<quantity>\d+(?:[,.]\d+)?)\s+"
            rf"(?P<unit_price>{amount})\s+"
            rf"(?P<amount>{amount})\s*$",
            compact_text(line),
            flags=re.IGNORECASE,
        )
        if match:
            rows.append(
                {
                    "designation": compact_text(match.group("designation")),
                    "article": match.group("article"),
                    "delivery_date": "",
                    "quantity": _to_natural_qty_str(match.group("quantity")),
                    "unit_price": compact_text(match.group("unit_price")),
                    "amount": compact_text(match.group("amount")),
                    "customer_reference": "",
                    "payment_terms": "",
                    "parser": "table_line_regex",
                }
            )
    if rows:
        return rows

    # Only attempt this fallback when OCR actually split content across lines.
    if len(lines) >= 2:
        return extract_line_items_from_multiline_lines(lines)
    return []


def extract_line_items_from_article_windows(text: str, materials_by_id: dict[str, str]) -> list[dict]:
    """Fallback extractor for OCRed PDFs where rows are broken across lines.

    Strategy: detect article-like ids, then mine quantity/price in a local window.
    """
    compact = compact_text(text)
    amount_re = re.compile(_amount_pattern(), flags=re.IGNORECASE)
    article_re = re.compile(r"\b(?P<art>(?:ELM|EL)?\d{7,10})\b", flags=re.IGNORECASE)
    rows: list[dict] = []
    seen_articles: set[str] = set()

    for m in article_re.finditer(compact):
        raw_article = m.group("art")
        article = _normalize_article_token(raw_article)
        if not re.fullmatch(r"\d{7,10}", article):
            continue
        if article in seen_articles:
            continue

        start = max(0, m.start() - 180)
        end = min(len(compact), m.end() + 220)
        window = compact[start:end]
        before = compact_text(window[: m.start() - start])
        after = compact_text(window[m.end() - start :])

        qty = ""
        unit = ""
        qty_match = re.search(
            r"(?<!\w)(?P<qty>\d{1,4}(?:[,.]\d{1,3})?)\s*(?P<unit>PCE|PCS|PIECE|PC|UN|EA)\b",
            before,
            flags=re.IGNORECASE,
        )
        if not qty_match:
            qty_match = re.search(
                r"(?<!\w)(?P<qty>\d{1,4}(?:[,.]\d{1,3})?)\s*(?P<unit>PCE|PCS|PIECE|PC|UN|EA)\b",
                after,
                flags=re.IGNORECASE,
            )
        if qty_match:
            qty = qty_match.group("qty")
            unit = qty_match.group("unit").upper().replace("PIECE", "PCE")

        unit_price = ""
        up = re.search(
            r"(?P<price>(?:\d{1,3}(?:[ ]\d{3})+|\d{1,6})[,.]\d{2})\s*(?:€|EUR)?\s*/\s*(?:PCE|PCS|PIECE|PC|UN|EA)",
            after,
            flags=re.IGNORECASE,
        )
        if not up:
            up = re.search(
                r"(?P<price>(?:\d{1,3}(?:[ ]\d{3})+|\d{1,6})[,.]\d{2})\s*(?:€|EUR)?",
                after,
                flags=re.IGNORECASE,
            )
        if up:
            unit_price = compact_text(up.group("price"))

        amounts = [compact_text(a.group(0)) for a in amount_re.finditer(window)]
        amount = amounts[-1] if amounts else ""

        designation = ""
        if before:
            tail = before[-120:]
            # keep only text-ish suffix before article id
            tail = re.sub(r"\b(?:ARTICLE|DESIGNATION|QTE|QUANTITE|PRIX|MONTANT|TOTAL)\b", " ", tail, flags=re.I)
            tail = re.sub(r"\s+", " ", tail).strip(" -:;,.")
            if tail:
                designation = tail
        if not designation:
            designation = materials_by_id.get(article, "")

        weak_context = bool(re.search(r"\b(article|designation|qte|quantite|prix|montant)\b", window, re.I))
        has_signals = bool(qty or unit_price or amount)
        has_masterdata_hint = article in materials_by_id
        # Keep weak candidates only when clearly in an article context.
        if not has_signals and not (has_masterdata_hint and weak_context):
            continue

        seen_articles.add(article)
        rows.append(
            {
                "designation": designation,
                "article": article,
                "delivery_date": "",
                "quantity": qty,
                "unit": unit,
                "unit_price": unit_price,
                "amount": amount,
                "customer_reference": "",
                "payment_terms": "",
                "designation_masterdata": materials_by_id.get(article, ""),
                "status": "candidate" if has_signals else "a_verifier",
                "parser": "article_window" if has_signals else "article_window_weak",
            }
        )

    return rows


def extract_line_items_from_layout(layout: dict | None) -> list[dict]:
    if not layout or not layout.get("lines"):
        return []
    lines = [line.get("text", "") for line in layout["lines"] if line.get("text")]
    return extract_line_items_from_lines(lines)


def extract_line_items(text: str, layout: dict | None, materials_by_id: dict[str, str]) -> list[dict]:
    rows = extract_line_items_from_layout(layout)
    if rows:
        return enrich_line_items_with_materials(rows, materials_by_id)
    return extract_line_items_from_text(text, materials_by_id)


def extract_line_items_from_text(text: str, materials_by_id: dict[str, str] | None = None) -> list[dict]:
    materials_by_id = materials_by_id or {}
    line_rows = extract_line_items_from_lines(text.splitlines())
    if line_rows:
        return enrich_line_items_with_materials(line_rows, materials_by_id)

    compact = compact_text(text)
    article_region_match = re.search(r"(?:Code article|Article).*", compact, flags=re.IGNORECASE)
    article_region = article_region_match.group(0) if article_region_match else compact
    amount = _amount_pattern()
    pattern = re.compile(
        rf"(?P<unit_price>{amount})\s+"
        rf"(?P<amount>{amount})\s+"
        r"(?P<date>\d{2}/\d{2}/\d{4})\s+"
        r"(?P<designation>.+?)\s+"
        r"(?P<article>[A-Z]{1,4}\d{5,}|\d{5,}|0)"
        r"(?:\s+(?P<packaging>\d+(?:[,.]\d+)?))?"
        r"(?:\s+(?P<quantity>\d+(?:[,.]\d+)?))?"
        rf"(?=\s+{amount}\s+{amount}\s+\d{{2}}/\d{{2}}/\d{{4}}|\s+Total\b|$)",
        flags=re.IGNORECASE,
    )
    article_first_pattern = re.compile(
        rf"(?P<article>[A-Z]{{1,4}}\d{{5,}}|\d{{5,}})\s+"
        r"(?P<designation>.+?)\s+"
        r"(?P<quantity>\d+(?:[,.]\d+)?)\s+"
        rf"(?P<unit_price>{amount})\s+"
        rf"(?P<amount>{amount})"
        r"(?=\s+TOTAL\b|\s+FRAIS\b|\s+[A-Z]{1,4}\d{5,}|\s+\d{5,}|$)",
        flags=re.IGNORECASE,
    )
    rows = []
    for match in pattern.finditer(compact):
        rows.append(
            {
                "designation": compact_text(match.group("designation")),
                "article": match.group("article"),
                "delivery_date": match.group("date"),
                "quantity": match.group("quantity") or "",
                "unit_price": compact_text(match.group("unit_price")),
                "amount": compact_text(match.group("amount")),
                "customer_reference": "",
                "payment_terms": "",
                "parser": "compact_regex",
            }
        )
    for match in article_first_pattern.finditer(article_region):
        row = {
            "designation": compact_text(match.group("designation")),
            "article": match.group("article"),
            "delivery_date": "",
            "quantity": match.group("quantity") or "",
            "unit_price": compact_text(match.group("unit_price")),
            "amount": compact_text(match.group("amount")),
            "customer_reference": "",
            "payment_terms": "",
            "parser": "compact_article_first",
        }
        if row not in rows:
            rows.append(row)
    material_rows = extract_line_items_from_material_windows(text, materials_by_id)
    for row in material_rows:
        if not any(existing.get("article") == row.get("article") for existing in rows):
            rows.append(row)
    article_window_rows = extract_line_items_from_article_windows(text, materials_by_id)
    for row in article_window_rows:
        if not any(existing.get("article") == row.get("article") for existing in rows):
            rows.append(row)
    return enrich_line_items_with_materials(rows, materials_by_id)


def extract_line_items_from_material_windows(text: str, materials_by_id: dict[str, str]) -> list[dict]:
    if not materials_by_id:
        return []
    compact = compact_text(text)
    rows = []
    seen = set()
    material_ids = set(re.findall(r"\b\d{7,10}\b", compact))
    for article in material_ids:
        if article not in materials_by_id or article in seen:
            continue
        seen.add(article)
        for match in re.finditer(re.escape(article), compact):
            start = max(0, match.start() - 140)
            end = min(len(compact), match.end() + 90)
            window = compact[start:end]
            before = compact_text(window[: match.start() - start])
            after = compact_text(window[match.end() - start :])
            quantity = ""
            unit = ""
            qty_match = re.search(r"(?<!\w)(?P<qty>\d{1,4})\s*(?P<unit>PCE|PCS|PC|UN|EA)\b", before, flags=re.I)
            if qty_match:
                quantity = qty_match.group("qty")
                unit = qty_match.group("unit").upper()
            price = ""
            price_match = re.search(r"(?P<price>(?:\d{1,3}(?:[ ]\d{3})+|\d{1,5})[,.]\d{2})\s*(?:€|EUR)?\s*/?\s*(?:PCE|PCS|PC|UN|EA)?", after, flags=re.I)
            if not price_match:
                price_match = re.search(r"(?P<price>(?:\d{1,3}(?:[ ]\d{3})+|\d{1,5})[,.]\d{2})\s*(?:€|EUR)?", before, flags=re.I)
            if price_match:
                price = price_match.group("price")
            designation = before
            if qty_match:
                designation = compact_text(before[qty_match.end() :])
            designation = re.sub(r"\b(?:PRIX PUBLIC|TOTAL|ARTICLE|DESIGNATION)\b.*$", "", designation, flags=re.I).strip(" -:;,.")
            if len(designation) > 120:
                designation = compact_text(designation[-120:])
            rows.append(
                {
                    "designation": designation or materials_by_id.get(article, ""),
                    "article": article,
                    "delivery_date": "",
                    "quantity": quantity,
                    "unit": unit,
                    "unit_price": price,
                    "amount": "",
                    "customer_reference": "",
                    "payment_terms": "",
                    "designation_masterdata": materials_by_id.get(article, ""),
                    "status": "a_verifier" if not quantity or not price else "candidate",
                    "parser": "material_window",
                }
            )
            break
    return rows
