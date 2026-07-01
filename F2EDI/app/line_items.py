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
    return r"(?:(?:\d{1,3}(?:[ .]\d{3})*|\d+)[,.]\d{2}\s?(?:EUR|E|euros?)?|\d+\.\d{2}\s?€?)"


def extract_line_items_from_lines(lines: list[str]) -> list[dict]:
    rows = []
    header_index = None
    for index, line in enumerate(lines):
        folded = fold_text(line)
        if "article" in folded and ("designation" in folded or "design" in folded):
            header_index = index
            break

    if header_index is None:
        return rows

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
                amounts = [cell for cell in cells if re.search(r"\d[,.]\d{2}", cell)]
                quantity_candidates = [cell for cell in cells if re.fullmatch(r"\d+(?:[,.]\d+)?", cell)]
                designation_cells = [
                    cell
                    for idx, cell in enumerate(cells)
                    if idx != article_idx and not re.fullmatch(r"\d+(?:[,.]\d+)?", cell) and not re.search(r"\d[,.]\d{2}", cell)
                ]
                row = {
                    "designation": compact_text(" ".join(designation_cells)),
                    "article": article,
                    "delivery_date": next((cell for cell in cells if re.fullmatch(r"\d{2}/\d{2}/\d{4}", cell)), ""),
                    "quantity": quantity_candidates[-2] if len(quantity_candidates) >= 2 else (quantity_candidates[0] if quantity_candidates else ""),
                    "unit_price": amounts[0] if amounts else "",
                    "amount": amounts[-1] if amounts else "",
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
                    "quantity": match.group("quantity"),
                    "unit_price": compact_text(match.group("unit_price")),
                    "amount": compact_text(match.group("amount")),
                    "parser": "table_line_regex",
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
                "quantity": match.group("quantity") or match.group("packaging") or "",
                "unit_price": compact_text(match.group("unit_price")),
                "amount": compact_text(match.group("amount")),
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
            "parser": "compact_article_first",
        }
        if row not in rows:
            rows.append(row)
    material_rows = extract_line_items_from_material_windows(text, materials_by_id)
    for row in material_rows:
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
            qty_match = re.search(r"(?<!\w)(?P<qty>\d{1,4})\s*(?P<unit>PCE|PCS|PC|UN|U|EA)\b", before, flags=re.I)
            if qty_match:
                quantity = qty_match.group("qty")
                unit = qty_match.group("unit").upper()
            price = ""
            price_match = re.search(r"(?P<price>(?:\d{1,3}(?:[ ]\d{3})+|\d{1,5})[,.]\d{2})\s*(?:€|EUR)?\s*/?\s*(?:PCE|PCS|PC|UN|U)?", after, flags=re.I)
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
                    "designation_masterdata": materials_by_id.get(article, ""),
                    "status": "a_verifier" if not quantity or not price else "candidate",
                    "parser": "material_window",
                }
            )
            break
    return rows
