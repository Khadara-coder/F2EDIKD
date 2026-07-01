from __future__ import annotations

import re

from app.text_utils import compact_text, fold_text, unique

_AMOUNT_CAPTURE = r"((?:\d{1,3}(?:[ .]\d{3})*|\d+),\d{2}\s?(?:EUR|E|euros?)?|\d+\.\d{2}\s?€?)"
_AMOUNT_SEARCH = r"(?:(?:\d{1,3}(?:[ .]\d{3})*|\d+),\d{2}\s?(?:EUR|E|euros?)?|\d+\.\d{2}\s?€?)"


def _label_pattern(label: str) -> str:
    return r"\s*".join(re.escape(part) for part in label.split())


def _first_amount_in_text(value: str) -> str | None:
    match = re.search(_AMOUNT_CAPTURE, value, flags=re.IGNORECASE)
    return compact_text(match.group(1)) if match else None


def find_label_amount(text: str, label: str) -> str | None:
    compact = compact_text(text)
    match = re.search(
        rf"{_label_pattern(label)}\s*[:.]?\s*{_AMOUNT_CAPTURE}",
        compact,
        flags=re.IGNORECASE,
    )
    if match:
        return compact_text(match.group(1))

    label_fold = fold_text(label)
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if label_fold not in fold_text(line):
            continue
        same_line = _first_amount_in_text(line)
        if same_line:
            return same_line
        for next_line in lines[index + 1 : index + 3]:
            amount = _first_amount_in_text(next_line)
            if amount:
                return amount
    return None


def _line_index_for_label(text: str, labels: list[str]) -> int | None:
    for index, line in enumerate(text.splitlines()):
        folded = fold_text(line)
        if any(fold_text(label) in folded for label in labels):
            return index
    return None


def rank_amounts_by_context(text: str, amounts: list[str], limit: int = 10) -> list[dict]:
    lines = text.splitlines()
    ranked = []
    ttc_index = _line_index_for_label(text, ["total ttc", "net a payer", "montant total"])
    ht_index = _line_index_for_label(text, ["total ht", "montant ht"])

    for amount in unique(amounts, limit=limit):
        amount_key = re.sub(r"\s+", "", amount)
        best_score = 0
        best_reason = "generic"
        line_indexes = [
            index
            for index, line in enumerate(lines)
            if amount_key and amount_key in re.sub(r"\s+", "", line)
        ]
        for line_index in line_indexes:
            score = 1
            reason = "line_match"
            if ttc_index is not None:
                distance = abs(line_index - ttc_index)
                if line_index == ttc_index + 1:
                    score += 150
                    reason = "under_total_ttc"
                elif distance <= 2:
                    score += 100 - (distance * 10)
                    reason = "near_total_ttc"
            elif ht_index is not None:
                distance = abs(line_index - ht_index)
                if line_index == ht_index + 1:
                    score += 90
                    reason = "under_total_ht"
                elif distance <= 2:
                    score += 60 - (distance * 10)
                    reason = "near_total_ht"
            if score > best_score:
                best_score = score
                best_reason = reason
        ranked.append({"montant": amount, "score": best_score, "raison": best_reason})

    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def extract_document_totals(text: str) -> dict[str, str | None]:
    total_ht = find_label_amount(text, "Total HT")
    total_ttc = find_label_amount(text, "Total TTC") or find_label_amount(text, "Net a payer")
    return {"Total HT": total_ht, "Total TTC": total_ttc}
