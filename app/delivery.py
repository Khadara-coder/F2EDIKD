from __future__ import annotations

import math
import re

from app.config import get_config, scoring_config
from app.layout_geometry import bbox_center
from app.street_types import expand_street_type_abbreviations, street_type_padded_tokens, street_type_regex_fragment
from app.text_utils import compact_text, fold_text, norm_key, significant_tokens


def clean_document_lines(text: str) -> list[str]:
    lines = []
    for raw_line in text.splitlines():
        raw_line = compact_text(raw_line)
        if not raw_line:
            continue
        if "|" in raw_line:
            cells = [compact_text(cell) for cell in raw_line.split("|")]
            for cell in cells:
                if cell and not re.fullmatch(r"[-: ]+", cell):
                    lines.append(cell)
        else:
            lines.append(raw_line)
    return lines


def is_street_line(line: str) -> bool:
    if is_organization_reference_line(line):
        return False
    normalized = expand_street_type_abbreviations(line)
    if re.match(r"^\d{5}\s+[a-z]", normalized):
        return False
    street_words = street_type_padded_tokens()
    padded = f" {normalized} "
    if re.match(r"^\d+[a-z]?\s+", normalized) and not any(word in padded for word in street_words):
        return False
    return bool(re.match(r"^\d+[a-z]?\s+", normalized)) or any(word in padded for word in street_words)


def extract_street_fragment(line: str) -> str:
    cleaned = compact_text(line)
    street_pattern = street_type_regex_fragment()
    match = re.search(
        rf"\b(?P<number>\d{{1,4}}[a-z]?|[il]{{2}})\s+(?P<street>{street_pattern}\b.+)",
        expand_street_type_abbreviations(cleaned),
        flags=re.IGNORECASE,
    )
    if not match:
        match = re.search(
            rf"\b(?P<number>\d{{1,4}}[a-z]?|[il]{{2}})\s+(?P<street>{street_pattern}\b.+)",
            cleaned,
            flags=re.IGNORECASE,
        )
    if not match:
        return cleaned if is_street_line(cleaned) else ""
    number = match.group("number")
    if fold_text(number) in {"ll", "ii", "il", "li"}:
        number = "11"
    number_match = re.search(rf"(?i)\b{re.escape(number)}\b", cleaned)
    if number_match is None and number == "11":
        number_match = re.search(r"\b(?:ll|ii|il|li)\b", cleaned, flags=re.IGNORECASE)
    street_match = re.search(rf"(?i)\b{street_pattern}\b.+", cleaned)
    if number_match and street_match and street_match.start() >= number_match.start():
        street = cleaned[street_match.start() :]
    elif number_match:
        street = cleaned[number_match.end() :].strip()
    else:
        street = match.group("street")
    street = re.split(r"\s+-\s+|\s+n[°o]\b|\s+no\b|\s+n\s+de\s+compte\b", street, maxsplit=1, flags=re.IGNORECASE)[0]
    return compact_text(f"{number} {street}")


def is_address_noise(line: str) -> bool:
    folded = fold_text(line)
    noise = get_config().get("noise_lines", [])
    return any(item in folded for item in noise) or is_delivery_table_noise(line)


def is_address_complement(line: str) -> bool:
    folded = fold_text(line)
    return bool(re.match(r"^(b\.?p\.?|cs|c\.?s\.?|cedex|bp|boite postale)\b", folded))


def is_false_postal_context(line: str) -> bool:
    folded = fold_text(line)
    for pattern in get_config().get("postal_false_positive_patterns", []):
        if re.search(pattern, folded, flags=re.IGNORECASE):
            return True
    return False


def internal_organization_fragments() -> list[str]:
    fragments: list[str] = []
    for rule in get_config().get("internal_company_addresses", []):
        for key in ("organization_fragments", "company_fragments"):
            fragments.extend(fold_text(item) for item in rule.get(key, []) if item)
    return fragments


def is_organization_reference_line(line: str) -> bool:
    folded = fold_text(line)
    if not folded:
        return False
    for fragment in internal_organization_fragments():
        if fragment in folded and re.match(r"^\d{3,5}\s+", folded):
            return True
    return False


def rule_matches_internal_address(rule: dict, folded: str) -> bool:
    postals = [norm_key(item) for item in rule.get("postals", [])]
    cities = [fold_text(item) for item in rule.get("cities", [])]
    street_fragments = [fold_text(item) for item in rule.get("street_fragments", [])]
    street_numbers = [str(item).strip() for item in rule.get("street_numbers", [])]
    org_fragments = [
        fold_text(item)
        for item in list(rule.get("organization_fragments", [])) + list(rule.get("company_fragments", []))
        if item
    ]

    has_postal = any(postal and re.search(rf"\b{re.escape(postal)}\b", folded) for postal in postals)
    has_city = any(city and city in folded for city in cities)
    has_street = any(fragment and fragment in folded for fragment in street_fragments)
    has_number = any(number and re.search(rf"\b{re.escape(number)}\b", folded) for number in street_numbers)
    has_org = any(fragment and fragment in folded for fragment in org_fragments)

    if street_numbers and has_street and has_number:
        return True

    has_core_address = has_postal and has_city and has_street
    if not has_core_address:
        return bool(has_street and has_number and (has_city or has_postal))

    if street_numbers:
        if has_number:
            return True
        return bool(has_org and has_core_address)
    if org_fragments:
        return bool(has_org and has_core_address)
    return True


def is_internal_company_text(text: str) -> bool:
    folded = fold_text(text)
    if not folded:
        return False
    for rule in get_config().get("internal_company_addresses", []):
        if rule_matches_internal_address(rule, folded):
            return True
    return False


def is_internal_company_window(lines: list[str], index: int, radius: int = 4) -> bool:
    start = max(0, index - radius)
    end = min(len(lines), index + radius + 1)
    current = fold_text(lines[index]) if 0 <= index < len(lines) else ""
    if not current:
        return False
    current_has_internal_marker = False
    for rule in get_config().get("internal_company_addresses", []):
        for postal in rule.get("postals", []):
            if postal and re.search(rf"\b{re.escape(str(postal))}\b", current):
                current_has_internal_marker = True
        for fragment in rule.get("street_fragments", []):
            if fold_text(fragment) in current:
                current_has_internal_marker = True
        for fragment in rule.get("organization_fragments", []):
            if fold_text(fragment) in current:
                current_has_internal_marker = True
        for fragment in rule.get("company_fragments", []):
            if fold_text(fragment) in current:
                current_has_internal_marker = True
    if not current_has_internal_marker:
        return False
    return is_internal_company_text(" ".join(lines[start:end]))


def is_internal_company_candidate(candidate: dict) -> bool:
    from app.postal_reference import city_compatible

    text = " ".join(
        str(candidate.get(key) or "")
        for key in (
            "Adresse complete",
            "Nom / service",
            "Rue",
            "Complement",
            "Code postal",
            "Ville",
            "Pays",
        )
    )
    if is_internal_company_text(text):
        return True

    postal = norm_key(str(candidate.get("Code postal") or ""))
    city = str(candidate.get("Ville") or "")
    street = str(candidate.get("Rue") or "")
    for rule in get_config().get("internal_company_addresses", []):
        rule_postals = [norm_key(item) for item in rule.get("postals", [])]
        rule_cities = [fold_text(item) for item in rule.get("cities", [])]
        if postal not in rule_postals:
            continue
        if not any(city_compatible(city, item) for item in rule_cities):
            continue
        street_fragments = [fold_text(item) for item in rule.get("street_fragments", [])]
        street_numbers = [str(item).strip() for item in rule.get("street_numbers", [])]
        folded_street = fold_text(street)
        if street and street_fragments and any(fragment and fragment in folded_street for fragment in street_fragments):
            return True
        if street and street_numbers:
            if not any(number and re.search(rf"\b{re.escape(number)}\b", folded_street) for number in street_numbers):
                continue
            return True
        if not street:
            return True
    return False


def is_excluded_negative_anchor(text: str) -> bool:
    folded = fold_text(text)
    for fragment in get_config().get("anchors", {}).get("negative_exclude", []):
        if fold_text(fragment) in folded:
            return True
    return False


def is_delivery_table_noise(line: str) -> bool:
    folded = fold_text(line)
    table_words = get_config().get("delivery_section_stop_words", [])
    return folded in {fold_text(word) for word in table_words}


def find_delivery_section_index(lines: list[str], start: int) -> int:
    stop_words = get_config().get("delivery_section_stop_words") or get_config().get("section_stop_words", [])
    for index in range(start, len(lines)):
        folded = fold_text(lines[index])
        if any(fold_text(word) in folded for word in stop_words):
            return index
    return len(lines)


def postal_city_from_lines(lines: list[str], start: int, end: int) -> tuple[int, str, str] | None:
    from app.postal_reference import best_valid_postal_city_pair, clean_city_fragment, is_acceptable_postal_city_validation, is_invalid_city_token, validate_postal_city

    for index in range(start, min(end, len(lines))):
        line = lines[index]
        if is_internal_company_window(lines, index):
            continue
        pair = best_valid_postal_city_pair(line)
        if pair:
            return index, pair["postal"], pair["city"]

        postal_match = re.search(r"\b(\d{2})\s+(\d{3})\b|\b(\d{5})\b", line)
        if not postal_match:
            continue
        postal_code = postal_match.group(1) + postal_match.group(2) if postal_match.group(1) else postal_match.group(3)
        if index + 1 < len(lines):
            next_line = lines[index + 1]
            if re.fullmatch(r"[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ' -]{2,}", next_line, flags=re.IGNORECASE):
                city = clean_city_fragment(next_line)
                validation = validate_postal_city(postal_code, city)
                if city and not is_invalid_city_token(city) and is_acceptable_postal_city_validation(validation):
                    return index, postal_code, city
    return None


def find_next_section_index(lines: list[str], start: int) -> int:
    stop_words = get_config().get("section_stop_words", [])
    for index in range(start, len(lines)):
        folded = fold_text(lines[index])
        if any(word in folded for word in stop_words):
            return index
    return len(lines)


def delivery_anchor_keyword_groups() -> tuple[list[str], list[str], list[str]]:
    cfg = get_config().get("anchors", {})
    primary = [fold_text(item) for item in cfg.get("delivery", [])]
    secondary = [fold_text(item) for item in cfg.get("delivery_secondary", [])]
    exclude = [fold_text(item) for item in cfg.get("delivery_exclude", [])]
    return primary, secondary, exclude


def all_delivery_anchor_keywords() -> list[str]:
    primary, secondary, _exclude = delivery_anchor_keyword_groups()
    return [*primary, *secondary]


def is_multiline_lieu_de_livraison(lines: list[str], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    current = fold_text(lines[index])
    nxt = fold_text(lines[index + 1])
    return current.rstrip().endswith("lieu de") and nxt.startswith("livraison")


def is_multiline_lieu_de_livraison_pair(current_line: str, next_line: str) -> bool:
    current = fold_text(current_line)
    nxt = fold_text(next_line)
    return current.rstrip().endswith("lieu de") and nxt.startswith("livraison")


def line_matches_delivery_anchor(line: str, keywords: list[str], exclude: list[str]) -> bool:
    folded = fold_text(line)
    if any(fragment in folded for fragment in exclude):
        return False
    return any(keyword in folded for keyword in keywords)


def find_delivery_label(lines: list[str]) -> tuple[int, int] | None:
    primary, secondary, exclude = delivery_anchor_keyword_groups()
    for index in range(len(lines) - 1):
        if is_multiline_lieu_de_livraison(lines, index):
            return index, 2
    for index, line in enumerate(lines):
        if line_matches_delivery_anchor(line, primary, exclude):
            return index, 1
    for index, line in enumerate(lines):
        if line_matches_delivery_anchor(line, secondary, exclude):
            return index, 1
    return None


def find_site_code(lines: list[str], postal_index: int, city: str) -> str | None:
    city_prefix = fold_text(city)[:3]
    for line in lines[postal_index + 1 : postal_index + 8]:
        value = compact_text(line)
        folded = fold_text(value)
        if is_address_noise(value) or any(stop in folded for stop in get_config().get("delivery_section_stop_words", [])):
            continue
        if re.fullmatch(r"[A-Z0-9]{2,8}", value) and fold_text(value) != "france":
            return value
        if city_prefix and folded.startswith(city_prefix) and len(value) <= 12:
            return value
    return None


def layout_anchor_kind(line_text: str, previous_line_text: str | None = None) -> str | None:
    folded = fold_text(line_text)
    if "mode livraison" in folded or "delai livraison" in folded:
        return None
    if previous_line_text and is_multiline_lieu_de_livraison_pair(previous_line_text, line_text):
        return "livraison"
    cfg = get_config().get("anchors", {})
    primary = [fold_text(item) for item in cfg.get("delivery", [])]
    secondary = [fold_text(item) for item in cfg.get("delivery_secondary", [])]
    delivery_exclude = [fold_text(item) for item in cfg.get("delivery_exclude", [])]
    billing_keywords = [fold_text(item) for item in cfg.get("negative", [])]
    if any(fragment in folded for fragment in delivery_exclude):
        return None
    if any(keyword in folded for keyword in primary):
        return "livraison"
    if any(keyword in folded for keyword in secondary):
        return "livraison"
    if any(keyword in folded for keyword in billing_keywords):
        if is_excluded_negative_anchor(line_text):
            return None
        return "negative"
    return None


def spatial_lieu_de_livraison_anchors(
    layout_lines: list[dict],
    page_width: float,
    page_height: float,
) -> list[dict]:
    from app.layout_geometry import union_bbox

    anchors: list[dict] = []
    y_tol = page_height * 0.03
    lieu_lines = [
        line
        for line in layout_lines
        if fold_text(line.get("text", "")).rstrip().endswith("lieu de")
    ]
    livraison_lines = [
        line
        for line in layout_lines
        if fold_text(line.get("text", "")).strip() in {"livraison", "livraison:"}
    ]
    for lieu_line in lieu_lines:
        lieu_box = lieu_line["bbox"]
        for liv_line in livraison_lines:
            liv_box = liv_line["bbox"]
            vertical_gap = float(liv_box["y0"]) - float(lieu_box["y1"])
            if vertical_gap < -y_tol or vertical_gap > y_tol * 3:
                if abs(float(liv_box["y0"]) - float(lieu_box["y0"])) > y_tol:
                    continue
            if not layout_same_column(lieu_box, liv_box, page_width):
                if abs(float(lieu_box["x0"]) - float(liv_box["x0"])) > page_width * 0.2:
                    continue
            bbox = union_bbox([lieu_box, liv_box])
            anchors.append({"kind": "livraison", "text": "LIEU DE LIVRAISON", "bbox": bbox})
    return anchors


def postal_city_from_text(line: str) -> tuple[str, str] | None:
    from app.postal_reference import best_valid_postal_city_pair, load_postal_reference

    pair = best_valid_postal_city_pair(line)
    if pair:
        return pair["postal"], pair["city"]

    reference = load_postal_reference()
    if reference["loaded"]:
        return None

    match = re.search(r"\b(\d{5})\b\s*([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ' -]{2,})?", line, flags=re.IGNORECASE)
    if not match:
        return None
    postal_code = match.group(1)
    city = compact_text(match.group(2) or "")
    if city:
        city = compact_text(re.split(r"\s{2,}|\s+-\s+|[,;|]", city, maxsplit=1)[0])
    return postal_code, city


def page_diagonal(page_width: float, page_height: float) -> float:
    return max(1.0, math.hypot(page_width, page_height))


def closest_anchor_to_candidate(
    candidate: dict,
    anchors: list[dict],
    *,
    use_postal_line: bool = True,
) -> tuple[float | None, dict | None]:
    if not anchors:
        return None, None
    best_distance = float("inf")
    best_anchor = None
    for anchor in anchors:
        distance = layout_anchor_distance(anchor, candidate, use_postal_line=use_postal_line)
        if distance < best_distance:
            best_distance = distance
            best_anchor = anchor
    return best_distance, best_anchor


def negative_anchors_for_proximity(
    negatives: list[dict],
    candidate: dict,
    page_height: float,
) -> list[dict]:
    postal_box = candidate.get("postal_bbox") or candidate.get("bbox") or {}
    postal_y = float(postal_box.get("y0", 0))
    margin = page_height * 0.012
    return [
        anchor
        for anchor in negatives
        if not is_excluded_negative_anchor(anchor.get("text", ""))
        and float(anchor["bbox"]["y0"]) < postal_y - margin
    ]


def delivery_anchor_claims_candidate(
    candidate: dict,
    delivery_anchor: dict | None,
    page_width: float,
    page_height: float,
) -> bool:
    if not delivery_anchor:
        return False
    postal_box = candidate.get("postal_bbox") or candidate.get("bbox")
    if not postal_box:
        return False
    anchor_box = delivery_anchor["bbox"]
    tolerance = page_height * 0.008
    if float(postal_box["y0"]) < float(anchor_box["y0"]) - tolerance:
        return False
    return layout_same_column(postal_box, anchor_box, page_width)


def layout_column_window_text(
    layout_lines: list[dict],
    index: int,
    page_width: float,
    *,
    radius: int = 3,
) -> str:
    if index < 0 or index >= len(layout_lines):
        return ""
    current_bbox = layout_lines[index]["bbox"]
    parts = [
        layout_lines[item].get("text", "")
        for item in range(max(0, index - radius), min(len(layout_lines), index + radius + 1))
        if layout_same_column(layout_lines[item]["bbox"], current_bbox, page_width)
    ]
    return " ".join(parts)


def candidate_vocabulary_proximity(
    candidate: dict,
    positives: list[dict],
    negatives: list[dict],
    page_width: float,
    page_height: float,
) -> dict:
    diagonal = page_diagonal(page_width, page_height)
    delivery_dist, delivery_anchor = closest_anchor_to_candidate(candidate, positives)
    negatives_for_compare = negative_anchors_for_proximity(negatives, candidate, page_height)
    billing_dist, billing_anchor = closest_anchor_to_candidate(candidate, negatives_for_compare)

    delivery_norm = round(delivery_dist / diagonal, 4) if delivery_dist is not None else None
    billing_norm = round(billing_dist / diagonal, 4) if billing_dist is not None else None

    if delivery_dist is None and billing_dist is None:
        closer_to_delivery = True
    elif delivery_dist is None:
        closer_to_delivery = False
    elif billing_dist is None:
        closer_to_delivery = True
    else:
        closer_to_delivery = delivery_dist < billing_dist

    if delivery_anchor and delivery_anchor_claims_candidate(candidate, delivery_anchor, page_width, page_height):
        closer_to_delivery = True

    margin_norm = None
    if delivery_dist is not None and billing_dist is not None:
        margin_norm = round((billing_dist - delivery_dist) / diagonal, 4)

    return {
        "Plus proche livraison que facturation": closer_to_delivery,
        "Distance livraison px": round(delivery_dist, 1) if delivery_dist is not None else None,
        "Distance facturation px": round(billing_dist, 1) if billing_dist is not None else None,
        "Distance livraison norm": delivery_norm,
        "Distance facturation norm": billing_norm,
        "Marge livraison vs facturation norm": margin_norm,
        "Ancre livraison la plus proche": delivery_anchor["text"] if delivery_anchor else None,
        "Ancre facturation la plus proche": billing_anchor["text"] if billing_anchor else None,
    }


def last_line_anchor_index_before(lines: list[str], before_index: int, keywords: list[str]) -> int | None:
    for index in range(before_index - 1, -1, -1):
        folded = fold_text(lines[index])
        if any(fold_text(keyword) in folded for keyword in keywords):
            return index
    return None


def postal_vocabulary_proximity(
    lines: list[str],
    line_index: int,
    line_text: str,
    postal_code: str,
    delivery_keywords: list[str],
    billing_keywords: list[str],
) -> tuple[bool, float]:
    folded = fold_text(line_text)
    delivery_positions = [folded.find(fold_text(keyword)) for keyword in delivery_keywords if fold_text(keyword) in folded]
    billing_positions = [folded.find(fold_text(keyword)) for keyword in billing_keywords if fold_text(keyword) in folded]
    postal_pos = line_text.find(postal_code)

    if delivery_positions and billing_positions and postal_pos >= 0:
        delivery_pos = min(position for position in delivery_positions if position >= 0)
        billing_pos = min(position for position in billing_positions if position >= 0)
        delivery_distance = abs(postal_pos - delivery_pos)
        billing_distance = abs(postal_pos - billing_pos)
        return delivery_distance < billing_distance, float(delivery_distance)

    delivery_index = last_line_anchor_index_before(lines, line_index, delivery_keywords)
    billing_index = last_line_anchor_index_before(lines, line_index, billing_keywords)

    if delivery_index is None and billing_index is None:
        return True, float(line_index)
    if delivery_index is None:
        return False, float("inf")
    if billing_index is None:
        return True, float(line_index - delivery_index)

    delivery_distance = float(line_index - delivery_index)
    billing_distance = float(line_index - billing_index)
    return delivery_distance < billing_distance, delivery_distance


def layout_same_column(a: dict, b: dict, page_width: float) -> bool:
    ax, _ay = bbox_center(a)
    bx, _by = bbox_center(b)
    overlaps = not (a["x1"] < b["x0"] or b["x1"] < a["x0"])
    return overlaps or abs(ax - bx) <= page_width * 0.22


def layout_relation_score(
    anchor: dict,
    candidate: dict,
    page_width: float,
    page_height: float,
    directional: bool = False,
) -> int:
    anchor_box = anchor["bbox"]
    candidate_box = candidate["bbox"]
    ax, ay = bbox_center(anchor_box)
    cx, cy = bbox_center(candidate_box)
    diagonal = max(1.0, math.hypot(page_width, page_height))
    distance = math.hypot(cx - ax, cy - ay)
    score = int(max(0, 45 * (1 - min(1, distance / (diagonal * 0.55)))))
    is_below = candidate_box["y0"] >= anchor_box["y0"] - 5
    is_right_same_band = candidate_box["x0"] >= anchor_box["x1"] - 5 and abs(cy - ay) <= page_height * 0.06
    if layout_same_column(anchor_box, candidate_box, page_width):
        score += 15
    if directional and not is_below and not is_right_same_band:
        score = int(score * 0.25)
    if is_below:
        score += 10
    elif is_right_same_band:
        score += 8
    return score


def layout_anchor_distance(anchor: dict, candidate: dict, use_postal_line: bool = False) -> float:
    anchor_box = anchor["bbox"]
    candidate_box = candidate.get("postal_bbox") if use_postal_line else candidate.get("bbox")
    candidate_box = candidate_box or candidate["bbox"]
    ax, ay = bbox_center(anchor_box)
    cx, cy = bbox_center(candidate_box)
    return math.hypot(cx - ax, cy - ay)


def layout_distance_score(anchor: dict, candidate: dict, page_width: float, page_height: float) -> tuple[int, float]:
    distance = layout_anchor_distance(anchor, candidate, use_postal_line=True)
    close_limit = max(1.0, math.hypot(page_width, page_height) * 0.28)
    score = int(max(0, 70 * (1 - min(1, distance / close_limit))))
    return score, distance


def delivery_anchor_position(anchor: dict, candidate: dict, page_height: float) -> str:
    anchor_box = anchor["bbox"]
    candidate_box = candidate.get("postal_bbox") or candidate["bbox"]
    _ax, ay = bbox_center(anchor_box)
    _cx, cy = bbox_center(candidate_box)
    if candidate_box["y0"] >= anchor_box["y0"] - 5:
        return "below"
    if candidate_box["x0"] >= anchor_box["x1"] - 5 and abs(cy - ay) <= page_height * 0.06:
        return "right"
    return "above"


def candidate_quality_score(candidate: dict) -> tuple[int, list[str]]:
    score = 0
    reasons = []
    if candidate.get("Code postal"):
        score += 25
        reasons.append("postal")
    if candidate.get("Ville"):
        score += 20
        reasons.append("city")
    if candidate.get("Rue"):
        score += 25
        reasons.append("street")
    if candidate.get("Nom / service"):
        score += 10
        reasons.append("name")
    validation = candidate.get("Validation code postal/ville") or {}
    if validation.get("match") is True:
        score += 15
        reasons.append("postal_city_ok")
    elif validation.get("match") is False:
        score -= 35
        reasons.append("postal_city_mismatch")
    return score, reasons


def add_postal_city_validation(candidate: dict) -> dict:
    from app.postal_reference import validate_postal_city

    validation = validate_postal_city(candidate.get("Code postal"), candidate.get("Ville"))
    if validation.get("match") is True and validation.get("matched_city"):
        candidate["Ville"] = validation["matched_city"]
    candidate["Validation code postal/ville"] = validation
    if validation.get("match") is True:
        candidate["Code postal/ville coherent"] = "oui"
    elif validation.get("match") is False:
        candidate["Code postal/ville coherent"] = "non"
    else:
        candidate["Code postal/ville coherent"] = "non verifie"
    return purify_delivery_address(candidate)


def remove_incompatible_postal_city_fragments(lines: list[str], selected_postal: str, selected_city: str) -> list[str]:
    from app.postal_reference import validate_postal_city

    cleaned = []
    for line in lines:
        remove_line = False
        value = line
        for match in re.finditer(r"\b(\d{4,5})\b\s*([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ' -]{2,})?", line, flags=re.IGNORECASE):
            postal = norm_key(match.group(1)).zfill(5)
            city = compact_text(match.group(2) or "")
            if len(match.group(1)) == 4 and match.start() == 0 and is_street_line(line):
                continue
            if postal == selected_postal:
                continue
            if city and validate_postal_city(postal, city).get("match") is True:
                continue
            if selected_city and city and norm_key(city) != norm_key(selected_city):
                value = compact_text((value[: match.start()] + value[match.end() :]).strip(" -,:;"))
                if not value:
                    remove_line = True
                break
        if not remove_line:
            cleaned.append(value)
    return cleaned


def strip_address_line_noise(line: str, selected_postal: str = "", selected_city: str = "") -> str:
    value = compact_text(line)
    if not value:
        return ""
    if is_internal_company_text(value):
        return ""

    if selected_postal:
        compatible_lines = remove_incompatible_postal_city_fragments([value], selected_postal, selected_city)
        value = compatible_lines[0] if compatible_lines else ""
    value = re.split(r"\b(?:tel|t[Ã©e]l|telephone|fax|mail|email|e-mail)\b\s*:?", value, maxsplit=1, flags=re.IGNORECASE)[0]
    if "@" in value:
        value = value.split("@", 1)[0]

    label_patterns = [
        r"^a\s+livrer\s+a\s+l['â€™ ]adresse\s+ci[- ]dessous\s*:?",
        r"^adresse\s+(?:de\s+)?livraison\s*:?",
        r"^dresse\s+de\s+livraison\s*:?",
        r"^livraison\s*:?",
        r"^destinataire\s*:?",
        r"^chantier\s*:?",
        r"^type\s+livraison\.?\s*",
        r"^livre\s+a\s*:?",
    ]
    for pattern in label_patterns:
        value = re.sub(pattern, "", value, flags=re.IGNORECASE).strip(" -:;,.")

    folded = fold_text(value)
    instruction_markers = [
        "a livrer a l adresse ci dessous",
        "adresse de livraison",
        "plusieurs de nos agences",
        "une seule adresse",
        "colisages separes",
        "identifier chaque colis",
        "ne seront pas retires",
        "designation",
        "quantite",
        "prix",
        "delai",
        "catalogue",
        "plan de vente",
    ]
    if not value or any(marker in folded for marker in instruction_markers):
        return ""
    if re.fullmatch(r"a\s+[A-Z][A-Z0-9&' -]{2,}", value, flags=re.IGNORECASE):
        value = compact_text(re.sub(r"^a\s+", "", value, flags=re.IGNORECASE))
        folded = fold_text(value)
    if folded in {"fr", "france"}:
        return "FRANCE"
    return compact_text(value.strip(" -:;,."))


def likely_service_line(line: str, postal_code: str = "", city: str = "") -> bool:
    value = strip_address_line_noise(line, postal_code, city)
    if not value:
        return False
    folded = fold_text(value)
    if folded == "france" or is_street_line(value):
        return False
    if is_address_complement(value):
        return False
    if postal_code and re.search(rf"\b{re.escape(postal_code)}\b", value):
        return False
    if city and fold_text(city) in folded:
        return False
    if re.search(r"\b\d{5}\b", value):
        return False
    return True


def purify_delivery_address(candidate: dict) -> dict:
    postal_code = str(candidate.get("Code postal") or "")
    city = str(candidate.get("Ville") or "")

    service_parts: list[str] = []
    for raw in re.split(r"\s*/\s*|\n", str(candidate.get("Nom / service") or "")):
        cleaned = strip_address_line_noise(raw, postal_code, city)
        if cleaned and likely_service_line(cleaned, postal_code, city) and cleaned not in service_parts:
            service_parts.append(cleaned)

    complete_lines = [compact_text(line) for line in str(candidate.get("Adresse complete") or "").splitlines()]
    for line in complete_lines:
        cleaned = strip_address_line_noise(line, postal_code, city)
        if cleaned and likely_service_line(cleaned, postal_code, city) and cleaned not in service_parts:
            service_parts.append(cleaned)

    street = strip_address_line_noise(str(candidate.get("Rue") or ""), postal_code, city)
    if street and not is_street_line(street):
        street = ""
    if not street:
        for line in complete_lines:
            cleaned = strip_address_line_noise(line, postal_code, city)
            fragment = extract_street_fragment(cleaned)
            if fragment and is_street_line(fragment):
                street = fragment
                break

    complement_parts: list[str] = []
    for raw in re.split(r"\s*/\s*|\n", str(candidate.get("Complement") or "")):
        cleaned = strip_address_line_noise(raw, postal_code, city)
        if cleaned and cleaned != street and cleaned not in complement_parts:
            complement_parts.append(cleaned)

    country = strip_address_line_noise(str(candidate.get("Pays") or ""), postal_code, city) or "FRANCE"
    postal_city_line = compact_text(f"{postal_code} {city}".strip())
    rebuilt_lines = [
        *service_parts[-2:],
        street,
        *complement_parts,
        postal_city_line,
        country,
    ]
    rebuilt_lines = [line for line in rebuilt_lines if line]
    rebuilt = "\n".join(rebuilt_lines)

    if rebuilt and rebuilt != candidate.get("Adresse complete"):
        candidate["Adresse complete brute"] = candidate.get("Adresse complete", "")
        candidate["Adresse nettoyee"] = "oui"
        candidate["Adresse complete"] = rebuilt
    candidate["Nom / service"] = " / ".join(service_parts[-2:]) or None
    candidate["Rue"] = street or None
    candidate["Complement"] = " / ".join(complement_parts) or None
    candidate["Pays"] = country
    return candidate


def build_layout_address_candidates(layout: dict) -> list[dict]:
    from app.layout_geometry import union_bbox
    from app.postal_reference import is_rejectable_postal_city_pair

    lines = layout.get("lines", [])
    page_width = float(layout.get("width") or 1)
    candidates = []
    for index, line in enumerate(lines):
        line_text = line.get("text", "")
        if is_false_postal_context(line_text):
            continue
        postal_city = postal_city_from_text(line_text)
        if not postal_city:
            continue
        postal_code, city = postal_city
        city_index = None
        if not city and index + 1 < len(lines):
            next_text = lines[index + 1].get("text", "")
            if re.fullmatch(r"[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ' -]{2,}", next_text, flags=re.IGNORECASE):
                city = compact_text(next_text)
                city_index = index + 1

        text_before_postal = compact_text(re.split(r"\b\d{5}\b", line.get("text", ""), maxsplit=1)[0])
        street = text_before_postal if text_before_postal and is_street_line(text_before_postal) else ""
        street_index = index if street else None
        for previous_index in range(index - 1, max(-1, index - 6), -1):
            previous_text = lines[previous_index].get("text", "")
            if is_address_noise(previous_text):
                continue
            if not layout_same_column(lines[previous_index]["bbox"], line["bbox"], page_width):
                continue
            if is_street_line(previous_text):
                street = previous_text
                street_index = previous_index
                break

        selected_indexes = {index}
        if city_index is not None:
            selected_indexes.add(city_index)
        street_lines = []
        name_lines = []
        start_block = max(0, index - 12)
        for block_index in range(start_block, index):
            block_text = lines[block_index].get("text", "")
            folded_block = fold_text(block_text)
            if (
                is_address_noise(block_text)
                or folded_block == "france"
                or "tel" in folded_block
                or "mail" in folded_block
            ):
                continue
            if not layout_same_column(lines[block_index]["bbox"], line["bbox"], page_width):
                continue
            if is_street_line(block_text):
                street_lines.append(block_text)
                selected_indexes.add(block_index)
            elif street_index is None or block_index < street_index:
                name_lines.append(block_text)
                selected_indexes.add(block_index)

        if street and street not in street_lines:
            street_lines.append(street)
        if not street and street_lines:
            street = street_lines[-1]
        complement = " / ".join(street_lines[:-1]) if len(street_lines) > 1 else ""

        country = ""
        for country_index in range(index + 1, min(len(lines), index + 8)):
            country_text = lines[country_index].get("text", "")
            if fold_text(country_text) != "france":
                continue
            if not layout_same_column(lines[country_index]["bbox"], line["bbox"], page_width):
                continue
            country = "FRANCE"
            selected_indexes.add(country_index)
            break

        selected_lines = [lines[item] for item in sorted(selected_indexes)]
        if not selected_lines:
            continue
        boxes = [item["bbox"] for item in selected_lines]
        bbox = union_bbox(boxes)
        address_lines = [
            *name_lines[-2:],
            *street_lines,
            compact_text(f"{postal_code} {city}"),
            country,
        ]
        address_lines = [item for item in address_lines if item]
        candidate = {
            "Adresse complete": "\n".join(address_lines),
            "Nom / service": " / ".join(name_lines[-2:]),
            "Rue": street,
            "Complement": complement,
            "Code postal": postal_code,
            "Ville": city,
            "Pays": country,
            "bbox": bbox,
            "postal_bbox": line["bbox"],
            "Coordonnees": f"{bbox['x0']:.0f},{bbox['y0']:.0f},{bbox['x1']:.0f},{bbox['y1']:.0f}",
        }
        add_postal_city_validation(candidate)
        validation = candidate.get("Validation code postal/ville") or {}
        if is_rejectable_postal_city_pair(
            candidate.get("Code postal"),
            candidate.get("Ville"),
            validation,
        ):
            continue
        quality, quality_reasons = candidate_quality_score(candidate)
        candidate["Score qualite"] = quality
        candidate["Raisons qualite"] = "+".join(quality_reasons)
        if is_internal_company_candidate(candidate):
            continue
        candidates.append(candidate)
    candidates.extend(build_anchor_delivery_address_candidates(layout))
    return candidates


def build_anchor_delivery_address_candidates(layout: dict) -> list[dict]:
    from app.layout_geometry import union_bbox
    from app.postal_reference import (
        best_postal_city_in_text,
        find_city_mentions,
        is_acceptable_postal_city_validation,
        is_rejectable_postal_city_pair,
        postals_for_city,
        validate_postal_city,
    )

    lines = layout.get("lines", [])
    if not lines:
        return []
    page_width = float(layout.get("width") or 1)
    page_height = float(layout.get("height") or 1)
    negative_anchors = []
    for line_index, line in enumerate(lines):
        previous_text = lines[line_index - 1].get("text", "") if line_index > 0 else None
        kind = layout_anchor_kind(line.get("text", ""), previous_text)
        if kind == "negative" or is_internal_company_text(line.get("text", "")):
            negative_anchors.append(line)
    candidates = []
    for anchor_index, anchor_line in enumerate(lines):
        previous_text = lines[anchor_index - 1].get("text", "") if anchor_index > 0 else None
        if layout_anchor_kind(anchor_line.get("text", ""), previous_text) != "livraison":
            continue

        anchor_box = anchor_line["bbox"]
        selected_indexes = {anchor_index}
        window_indexes = []
        for index in range(anchor_index + 1, min(len(lines), anchor_index + 9)):
            line = lines[index]
            bbox = line["bbox"]
            if bbox["y0"] < anchor_box["y0"] - 5:
                continue
            if not layout_same_column(anchor_box, bbox, page_width):
                continue
            text = line.get("text", "")
            folded = fold_text(text)
            if any(stop in folded for stop in get_config().get("delivery_section_stop_words", [])) and not is_street_line(text):
                break
            if is_internal_company_text(text):
                continue
            window_indexes.append(index)

        if not window_indexes:
            continue

        window_text = " ".join(lines[index].get("text", "") for index in window_indexes)
        text_pair = best_postal_city_in_text(window_text)
        street = ""
        street_index = None
        for index in window_indexes:
            fragment = extract_street_fragment(lines[index].get("text", ""))
            if fragment:
                street = fragment
                street_index = index
                selected_indexes.add(index)
                break

        city = ""
        postal_code = ""
        if text_pair:
            city = text_pair["city"]
            postal_code = text_pair["postal"]
        city_mentions = find_city_mentions(window_text, min_length=5)
        if not city and city_mentions:
            for mention in city_mentions:
                mention_city = mention["city"].upper()
                postals = mention["postals"]
                if len(postals) != 1:
                    continue
                validation = validate_postal_city(postals[0], mention_city)
                if not is_acceptable_postal_city_validation(validation):
                    continue
                city = mention_city
                postal_code = postals[0]
                break

        if not postal_code and city:
            postals = postals_for_city(city)
            if len(postals) == 1:
                postal_code = postals[0]
        if not city:
            continue
        if not street and not postal_code:
            continue

        name_lines = []
        for index in window_indexes:
            if index == street_index:
                continue
            text = compact_text(lines[index].get("text", ""))
            folded = fold_text(text)
            if (
                not text
                or is_address_noise(text)
                or "delai" in folded
                or "devise" in folded
                or "reliquat" in folded
                or "par vos soins" in folded
                or "franco" in folded
                or "@" in text
            ):
                continue
            if postal_code and postal_code in text:
                selected_indexes.add(index)
                continue
            if city and fold_text(city) in folded:
                selected_indexes.add(index)
                continue
            if city and fold_text(city) in folded and len(text) > 40:
                selected_indexes.add(index)
                continue
            if len(name_lines) < 2:
                name_lines.append(text)
                selected_indexes.add(index)

        if postal_code and city:
            name_lines = remove_incompatible_postal_city_fragments(name_lines, postal_code, city)

        selected_lines = [lines[index] for index in sorted(selected_indexes)]
        bbox = union_bbox([item["bbox"] for item in selected_lines])
        address_lines = [
            *name_lines[-2:],
            street,
            compact_text(f"{postal_code} {city}") if postal_code else city,
            "FRANCE",
        ]
        candidate = {
            "Adresse complete": "\n".join(line for line in address_lines if line),
            "Nom / service": " / ".join(name_lines[-2:]),
            "Rue": street,
            "Complement": "",
            "Code postal": postal_code,
            "Ville": city,
            "Pays": "FRANCE",
            "bbox": bbox,
            "postal_bbox": selected_lines[-1]["bbox"],
            "Coordonnees": f"{bbox['x0']:.0f},{bbox['y0']:.0f},{bbox['x1']:.0f},{bbox['y1']:.0f}",
            "Source candidat": "ancre_livraison",
            "CP infere depuis ville": "oui" if postal_code and not text_pair else "non",
            "CP choisi par reference ville": "oui" if text_pair else "non",
        }
        add_postal_city_validation(candidate)
        validation = candidate.get("Validation code postal/ville") or {}
        if is_rejectable_postal_city_pair(
            candidate.get("Code postal"),
            candidate.get("Ville"),
            validation,
        ):
            continue
        quality, quality_reasons = candidate_quality_score(candidate)
        candidate["Score qualite"] = quality
        candidate["Raisons qualite"] = "+".join([*quality_reasons, "delivery_anchor_block"])
        if not is_internal_company_candidate(candidate):
            delivery_dist = layout_anchor_distance({"bbox": anchor_box}, candidate, use_postal_line=True)
            negative_dist, _negative_anchor = closest_anchor_to_candidate(candidate, negative_anchors)
            if negative_dist is not None and negative_dist + page_height * 0.02 < delivery_dist:
                continue
            candidates.append(candidate)
    return candidates


def layout_column_band(bbox: dict, page_width: float) -> str:
    cx, _ = bbox_center(bbox)
    if cx <= page_width * 0.42:
        return "left"
    if cx >= page_width * 0.58:
        return "right"
    return "center"


def address_from_layout_candidate(candidate: dict) -> dict:
    score = int(candidate.get("Score geometrie", 0))
    return {
        "Statut": "Detectee par geometrie",
        "Confiance": "elevee" if score >= 80 else "moyenne",
        "Source": "coordonnees document",
        "Score geometrie": score,
        "Raisons geometrie": candidate.get("Raisons geometrie", ""),
        "Ancre positive": candidate.get("Ancre positive", ""),
        "Distance livraison px": candidate.get("Distance livraison px", ""),
        "Distance facturation px": candidate.get("Distance facturation px", ""),
        "Distance livraison norm": candidate.get("Distance livraison norm", ""),
        "Plus proche livraison que facturation": candidate.get("Plus proche livraison que facturation", ""),
        "Position ancre positive": candidate.get("Position ancre positive", ""),
        "Code postal/ville coherent": candidate.get("Code postal/ville coherent", ""),
        "Validation code postal/ville": candidate.get("Validation code postal/ville", {}),
        "Ancre negative": candidate.get("Ancre negative", ""),
        "Coordonnees": candidate.get("Coordonnees", ""),
        "Nom / service": candidate.get("Nom / service") or None,
        "Rue": candidate.get("Rue") or None,
        "Complement": candidate.get("Complement") or None,
        "Code postal": candidate.get("Code postal") or None,
        "Ville": candidate.get("Ville") or None,
        "Pays": candidate.get("Pays") or "FRANCE",
        "Adresse complete": candidate.get("Adresse complete", ""),
    }


def score_text_delivery_candidate(address: dict) -> int:
    status = address.get("Statut", "")
    if status == "Detectee":
        score = 50
    elif status == "Libelle trouve mais adresse non reconstruite":
        return 15
    elif status == "Non detectee":
        return 0
    else:
        return 0

    if address.get("Code postal"):
        score += 20
    if address.get("Ville"):
        score += 15
    if address.get("Rue"):
        score += 15
    else:
        score -= 35
    if address.get("Nom / service"):
        score += 10

    validation = address.get("Validation code postal/ville") or {}
    if validation.get("match") is True:
        score += 15
    elif validation.get("match") is False:
        score -= 35

    if address.get("Confiance") == "elevee":
        score += 20
    elif address.get("Confiance") == "moyenne":
        score -= 30

    street = address.get("Rue") or ""
    if re.search(r"\b\d{5}\b", street):
        score -= 25
    if len(re.findall(r"\b\d{5}\b", address.get("Adresse complete", ""))) > 1:
        score -= 35
    if street and len(street) > 60:
        score -= 15
    service = address.get("Nom / service") or ""
    if service and re.search(r"\b\d{4,5}\b", service):
        score -= 30
    folded_address = fold_text(address.get("Adresse complete", ""))
    address_lines = [line for line in address.get("Adresse complete", "").splitlines() if compact_text(line)]
    if len(address_lines) > 8:
        score -= 45
    product_or_instruction_markers = [
        "designation",
        "quantite",
        "prix",
        "climatisation",
        "classe chauffage",
        "classe froid",
        "eco participation",
        "colisages separes",
        "identifier chaque colis",
        "ne seront pas retires",
        "catalogue",
        "plan de vente",
    ]
    if any(marker in folded_address for marker in product_or_instruction_markers):
        score -= 70
    if is_internal_company_candidate(address):
        score -= 120
    return max(0, score)


def resolve_delivery_address(
    text: str,
    filename: str | None = None,
    layout: dict | None = None,
    layout_analysis: dict | None = None,
) -> dict:
    from app.postal_reference import is_acceptable_postal_city_validation

    cfg = scoring_config()
    if layout_analysis is None:
        layout_analysis = analyze_delivery_layout(layout)

    text_address = extract_delivery_address(text, filename)
    options: list[tuple[str, dict, int]] = []

    text_score = score_text_delivery_candidate(text_address)
    if text_score > 0:
        text_copy = dict(text_address)
        text_copy["Source"] = "texte"
        options.append(("texte", text_copy, text_score))

    min_geo = int(cfg.get("delivery_resolve_layout_min_score", 70))
    for candidate in layout_analysis.get("address_candidates", []):
        if not candidate.get("Plus proche livraison que facturation", True):
            continue
        geo_score = int(candidate.get("Score geometrie", 0))
        if geo_score < min_geo:
            continue
        if candidate.get("Position ancre positive") == "above":
            geo_score = int(geo_score * cfg.get("layout_above_anchor_factor", 0.35))
        if not candidate.get("Code postal") or not candidate.get("Ville"):
            continue
        geo_address = address_from_layout_candidate(candidate)
        if is_internal_company_candidate(geo_address):
            continue
        options.append(("geometrie", geo_address, geo_score))

    if not options:
        return text_address

    options.sort(
        key=lambda item: (
            not is_acceptable_postal_city_validation((item[1].get("Validation code postal/ville") or {})),
            (item[1].get("Validation code postal/ville") or {}).get("match") is not True,
            -item[2],
        )
    )
    winner_source, winner, winner_score = options[0]
    resolved = dict(winner)
    resolved["Source retenue"] = winner_source
    resolved["Score resolution"] = winner_score

    if len(options) > 1:
        alt_source, alt_address, alt_score = options[1]
        resolved["Alternative detectee"] = {
            "Source": alt_source,
            "Code postal": alt_address.get("Code postal"),
            "Ville": alt_address.get("Ville"),
            "Score": alt_score,
        }

    if winner_source == "geometrie" and text_address.get("Code postal"):
        resolved["Adresse texte brute"] = {
            "Code postal": text_address.get("Code postal"),
            "Ville": text_address.get("Ville"),
            "Rue": text_address.get("Rue"),
            "Confiance": text_address.get("Confiance"),
        }
    elif winner_source == "texte" and len(options) > 1 and options[1][0] == "geometrie":
        geo = options[1][1]
        if geo.get("Code postal") and norm_key(str(geo.get("Code postal"))) != norm_key(str(resolved.get("Code postal"))):
            resolved["Adresse geometrie ecartee"] = {
                "Code postal": geo.get("Code postal"),
                "Ville": geo.get("Ville"),
                "Score geometrie": geo.get("Score geometrie"),
            }

    return resolved


def extract_billing_postal_hints(text: str) -> list[str]:
    lines = clean_document_lines(text)
    delivery_keywords = all_delivery_anchor_keywords()
    delivery_index = next(
        (
            index
            for index, line in enumerate(lines)
            if any(fold_text(keyword) in fold_text(line) for keyword in delivery_keywords)
        ),
        len(lines),
    )
    postals: list[str] = []
    start = min(3, delivery_index)
    for line in lines[start:delivery_index]:
        if is_false_postal_context(line):
            continue
        for match in re.finditer(r"\b(\d{5})\b", line):
            postal = match.group(1)
            if postal not in postals:
                postals.append(postal)
    return postals


def collect_delivery_address_candidates(
    text: str,
    filename: str | None = None,
    layout: dict | None = None,
    layout_analysis: dict | None = None,
) -> list[dict]:
    if layout_analysis is None:
        layout_analysis = analyze_delivery_layout(layout)

    candidates: list[dict] = []
    seen: set[str] = set()

    def add_candidate(address: dict, source: str, score: int) -> None:
        key = norm_key(
            f"{address.get('Code postal', '')}|{address.get('Ville', '')}|{address.get('Rue', '')}|{source}"
        )
        if key in seen or not address.get("Code postal"):
            return
        seen.add(key)
        item = dict(address)
        item["Source"] = source
        item["Score resolution"] = score
        candidates.append(item)

    text_address = extract_delivery_address(text, filename)
    text_score = score_text_delivery_candidate(text_address)
    if text_score > 0:
        add_candidate(text_address, "texte", text_score)

    cfg = scoring_config()
    min_geo = int(cfg.get("delivery_resolve_layout_min_score", 70))
    for layout_candidate in layout_analysis.get("address_candidates", []):
        if not layout_candidate.get("Plus proche livraison que facturation", True):
            continue
        geo_score = int(layout_candidate.get("Score geometrie", 0))
        if geo_score < min_geo:
            continue
        if not layout_candidate.get("Code postal") or not layout_candidate.get("Ville"):
            continue
        geo_address = address_from_layout_candidate(layout_candidate)
        if is_internal_company_candidate(geo_address):
            continue
        add_candidate(geo_address, "geometrie", geo_score)

    heuristic = resolve_delivery_address(text, filename, layout, layout_analysis)
    if heuristic.get("Code postal"):
        add_candidate(
            heuristic,
            heuristic.get("Source retenue", heuristic.get("Source", "heuristique")),
            int(heuristic.get("Score resolution", 0)),
        )

    candidates.sort(key=lambda item: int(item.get("Score resolution", 0)), reverse=True)
    return candidates


def layout_is_ocr(layout: dict | None) -> bool:
    source = fold_text(str((layout or {}).get("source", "")))
    return source.startswith("ocr")


def trusted_ocr_delivery_candidate(candidate: dict) -> bool:
    from app.postal_reference import is_acceptable_postal_city_validation

    validation = candidate.get("Validation code postal/ville") or {}
    if not is_acceptable_postal_city_validation(validation):
        return False
    if validation.get("match") is not True:
        return False
    return bool(candidate.get("Code postal")) and bool(candidate.get("Ville"))


def delivery_anchor_claims_relaxed(
    candidate: dict,
    delivery_anchor: dict | None,
    page_width: float,
    page_height: float,
    *,
    layout: dict | None = None,
) -> bool:
    if delivery_anchor_claims_candidate(candidate, delivery_anchor, page_width, page_height):
        return True
    if not layout_is_ocr(layout) or not trusted_ocr_delivery_candidate(candidate):
        return False
    if not delivery_anchor:
        return False
    postal_box = candidate.get("postal_bbox") or candidate.get("bbox")
    if not postal_box:
        return False
    anchor_box = delivery_anchor["bbox"]
    return layout_same_column(postal_box, anchor_box, page_width)


def postal_city_matches_in_lines(
    lines: list[str],
    start: int,
    end: int,
) -> list[tuple[int, str, str, str]]:
    from app.postal_reference import extract_postal_city_pairs, is_rejectable_postal_city_pair

    matches: list[tuple[int, str, str, str]] = []
    for index in range(start, min(end, len(lines))):
        line = lines[index]
        if is_internal_company_window(lines, index):
            continue
        line_pairs = []
        for pair in extract_postal_city_pairs(line):
            if is_rejectable_postal_city_pair(pair["postal"], pair.get("city"), pair.get("validation")):
                continue
            line_pairs.append((index, pair["postal"], pair["city"], line))
        if not line_pairs and is_false_postal_context(line):
            continue
        matches.extend(line_pairs)
    return matches


def postal_city_from_delivery_section(
    lines: list[str],
    start: int,
    end: int,
    *,
    interleaved: bool,
) -> tuple[int, str, str] | None:
    cfg = get_config().get("anchors", {})
    delivery_keywords = all_delivery_anchor_keywords()
    billing_keywords = cfg.get("negative", [])

    matches = postal_city_matches_in_lines(lines, start, end)
    if not matches:
        expanded_start = max(0, start - 25)
        if expanded_start < start:
            matches = postal_city_matches_in_lines(lines, expanded_start, start)

    if not matches:
        return postal_city_from_lines(lines, start, end)

    ranked: list[tuple[bool, float, tuple[int, str, str]]] = []
    for index, postal_code, city, line in matches:
        closer_to_delivery, delivery_distance = postal_vocabulary_proximity(
            lines,
            index,
            line,
            postal_code,
            delivery_keywords,
            billing_keywords,
        )
        header_penalty = max(0, start - index) * 3.0 if index < start else 0.0
        ranked.append((closer_to_delivery, delivery_distance + header_penalty, (index, postal_code, city)))

    winners = [item for item in ranked if item[0]]
    if winners:
        _closer, _distance, chosen = min(winners, key=lambda item: item[1])
        return chosen

    if interleaved and len(matches) > 1:
        return matches[-1][:3]
    return min(ranked, key=lambda item: item[1])[2]


def analyze_delivery_layout(layout: dict | None) -> dict:
    from app.postal_reference import is_acceptable_postal_city_validation

    if not layout or not layout.get("lines"):
        return {"address_candidates": [], "candidate_summaries": [], "anchor_summaries": []}

    cfg = scoring_config()
    page_width = float(layout.get("width") or 1)
    page_height = float(layout.get("height") or 1)
    layout_lines = layout.get("lines", [])
    anchors = spatial_lieu_de_livraison_anchors(layout_lines, page_width, page_height)
    for index, line in enumerate(layout_lines):
        previous_text = layout_lines[index - 1].get("text", "") if index > 0 else None
        kind = layout_anchor_kind(line.get("text", ""), previous_text)
        if kind:
            anchors.append({"kind": kind, "text": line.get("text", ""), "bbox": line["bbox"]})
        window_text = layout_column_window_text(layout_lines, index, page_width)
        if kind != "livraison" and is_internal_company_text(window_text):
            anchors.append({"kind": "negative", "text": f"adresse interne: {line.get('text', '')}", "bbox": line["bbox"]})

    positives = [anchor for anchor in anchors if anchor["kind"] == "livraison"]
    negatives = [anchor for anchor in anchors if anchor["kind"] == "negative"]
    require_closer = bool(cfg.get("layout_require_closer_to_delivery", True))
    margin_norm_min = float(cfg.get("layout_vocabulary_margin_norm", 0.01))
    candidates = []
    seen = set()
    for candidate in build_layout_address_candidates(layout):
        key = norm_key(f"{candidate.get('Rue', '')}|{candidate.get('Code postal', '')}|{candidate.get('Ville', '')}")
        if key in seen:
            continue
        if is_internal_company_candidate(candidate):
            continue

        proximity = candidate_vocabulary_proximity(candidate, positives, negatives, page_width, page_height)
        candidate.update(proximity)
        if positives:
            _delivery_distance, primary_delivery = closest_anchor_to_candidate(candidate, positives)
            if primary_delivery and not delivery_anchor_claims_relaxed(
                candidate,
                primary_delivery,
                page_width,
                page_height,
                layout=layout,
            ):
                continue
        if (
            require_closer
            and positives
            and negatives
            and not proximity["Plus proche livraison que facturation"]
        ):
            continue

        quality_score = int(candidate.get("Score qualite", 0))
        positive_scores = [
            (*layout_distance_score(anchor, candidate, page_width, page_height), anchor)
            for anchor in positives
        ]
        negative_scores = [
            (layout_relation_score(anchor, candidate, page_width, page_height), anchor) for anchor in negatives
        ]
        best_positive = max(positive_scores, key=lambda item: item[0], default=(0, 0.0, None))
        best_negative = max(negative_scores, key=lambda item: item[0], default=(0, None))
        negative_penalty = int(best_negative[0] * 0.65) if best_negative[1] else 0
        total = max(0, quality_score + best_positive[0] - negative_penalty)
        reasons = [candidate.get("Raisons qualite", "")]
        if best_positive[2]:
            reasons.append("near_delivery_anchor")
            candidate["Ancre positive"] = best_positive[2]["text"]
            if proximity["Distance livraison px"] is None:
                candidate["Distance livraison px"] = round(best_positive[1], 1)
            candidate["Position ancre positive"] = delivery_anchor_position(best_positive[2], candidate, page_height)
            if candidate["Position ancre positive"] == "above":
                if layout_is_ocr(layout) and trusted_ocr_delivery_candidate(candidate):
                    reasons.append("ocr_above_anchor")
                else:
                    total = int(total * cfg["layout_above_anchor_factor"])
                    reasons.append("above_delivery_anchor")
        if candidate.get("Source candidat") == "ancre_livraison" and best_positive[2]:
            total += int(cfg.get("layout_delivery_anchor_block_bonus", 25))
            reasons.append("delivery_anchor_block_bonus")
        if best_negative[1]:
            reasons.append("near_negative_anchor")
            candidate["Ancre negative"] = best_negative[1]["text"]
        if proximity.get("Marge livraison vs facturation norm") is not None:
            margin_norm = float(proximity["Marge livraison vs facturation norm"])
            if margin_norm >= margin_norm_min:
                vocabulary_bonus = int(min(35, margin_norm * 400))
                total += vocabulary_bonus
                reasons.append("vocabulary_proximity")
        if best_positive[2] and best_negative[1]:
            pos_col = layout_column_band(best_positive[2]["bbox"], page_width)
            neg_col = layout_column_band(best_negative[1]["bbox"], page_width)
            cand_col = layout_column_band(candidate["bbox"], page_width)
            if candidate.get("Source candidat") == "ancre_livraison":
                total += int(cfg.get("layout_delivery_column_bonus", 12))
                reasons.append("delivery_anchor_block")
            elif pos_col != neg_col and cand_col == neg_col:
                total = max(0, total - int(cfg.get("layout_billing_column_penalty", 45)))
                reasons.append("billing_column")
            elif layout_same_column(best_positive[2]["bbox"], candidate["bbox"], page_width):
                total += int(cfg.get("layout_delivery_column_bonus", 12))
                reasons.append("delivery_column")
        candidate["Score geometrie"] = min(100, total)
        candidate["Raisons geometrie"] = "+".join(reason for reason in reasons if reason)
        seen.add(key)
        candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            not is_acceptable_postal_city_validation(item.get("Validation code postal/ville") or {}),
            (item.get("Validation code postal/ville") or {}).get("match") is not True,
            not item.get("Plus proche livraison que facturation", True),
            item.get("Distance livraison norm") if item.get("Distance livraison norm") is not None else 999.0,
            -item.get("Score geometrie", 0),
        ),
    )
    anchor_summaries = [
        f"{anchor['kind']} @ {anchor['bbox']['x0']:.0f},{anchor['bbox']['y0']:.0f} - {anchor['text']}"
        for anchor in anchors[:12]
    ]
    candidate_summaries = [
        (
            f"{candidate.get('Score geometrie', 0)} - {candidate.get('Code postal', '')} {candidate.get('Ville', '')} - "
            f"{candidate.get('Rue', '')} - d={candidate.get('Distance livraison px', '')} - "
            f"{candidate.get('Coordonnees', '')} - {candidate.get('Raisons geometrie', '')}"
        )
        for candidate in candidates[:12]
    ]
    return {
        "address_candidates": candidates[:12],
        "candidate_summaries": candidate_summaries,
        "anchor_summaries": anchor_summaries,
    }


def delivery_address_from_layout(layout_analysis: dict | None) -> dict | None:
    min_score = int(scoring_config()["layout_delivery_min_score"])
    for candidate in (layout_analysis or {}).get("address_candidates", []):
        score = int(candidate.get("Score geometrie", 0))
        if score < min_score or not candidate.get("Ancre positive"):
            continue
        if candidate.get("Position ancre positive") == "above":
            continue
        if not candidate.get("Code postal") or not candidate.get("Ville"):
            continue
        return address_from_layout_candidate(candidate)
    return None


def extract_delivery_address(text: str, filename: str | None = None) -> dict:
    lines = clean_document_lines(text)
    label = find_delivery_label(lines)
    if label is None:
        return {
            "Statut": "Non detectee",
            "Confiance": "faible",
            "Adresse complete": "",
        }

    label_index, skip_lines = label
    section_start = label_index + skip_lines
    section_end = find_delivery_section_index(lines, section_start)
    interleaved_with_billing = any(
        any(fold_text(keyword) in fold_text(line) for keyword in get_config().get("anchors", {}).get("negative", []))
        for line in lines[label_index:section_end]
    )
    postal = postal_city_from_delivery_section(
        lines,
        section_start,
        section_end,
        interleaved=interleaved_with_billing,
    )
    if postal is None:
        return {
            "Statut": "Libelle trouve mais adresse non reconstruite",
            "Confiance": "faible",
            "Adresse complete": "",
        }

    postal_index, postal_code, city = postal

    street_search_start = max(0, section_start - 20)
    street_index = None
    for index in range(postal_index - 1, street_search_start - 1, -1):
        if not is_street_line(lines[index]) or is_address_noise(lines[index]):
            continue
        if is_internal_company_window(lines, index) or is_organization_reference_line(lines[index]):
            continue
        street_index = index
        break

    name_lines = []
    complement_lines = []
    if street_index is not None:
        if not interleaved_with_billing:
            name_lines = [
                line
                for line in lines[section_start:street_index]
                if not is_address_noise(line) and fold_text(line) != "france"
            ]
            complement_lines = [
                line
                for line in lines[street_index + 1 : postal_index]
                if not is_address_noise(line)
                and not is_street_line(line)
                and fold_text(line) != "france"
            ]
        street = extract_street_fragment(lines[street_index]) or lines[street_index]
    else:
        street = ""
        for index in range(postal_index - 1, street_search_start - 1, -1):
            line = lines[index]
            if is_address_noise(line) or fold_text(line) == "france":
                continue
            if is_internal_company_window(lines, index) or is_organization_reference_line(line):
                continue
            if is_street_line(line):
                street = extract_street_fragment(line) or line
                street_index = index
                break
            if is_address_complement(line):
                complement_lines.append(line)
            elif not interleaved_with_billing:
                name_lines.append(line)

    country = next((line for line in lines[postal_index + 1 : postal_index + 8] if fold_text(line) == "france"), "")
    site_code = find_site_code(lines, postal_index, city)
    if site_code and site_code not in name_lines:
        name_lines = [site_code, *name_lines]

    address_lines = [
        *name_lines,
        street,
        *complement_lines,
        f"{postal_code} {city}",
        country or "France",
    ]
    address_lines = [line for line in address_lines if line]

    address = {
        "Statut": "Detectee",
        "Confiance": "moyenne" if interleaved_with_billing else "elevee",
        "Site": site_code,
        "Nom / service": " / ".join(name_lines) if name_lines else None,
        "Rue": street or None,
        "Complement": " / ".join(complement_lines) if complement_lines else None,
        "Code postal": postal_code,
        "Ville": city,
        "Pays": country or "France",
        "Adresse complete": "\n".join(address_lines),
    }
    return add_postal_city_validation(address)
