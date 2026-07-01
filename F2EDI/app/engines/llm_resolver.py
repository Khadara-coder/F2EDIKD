"""LLM-based extraction and validation using Claude Sonnet 4.

Two roles:
1. llm_extract(): Fallback when rule-based engine returns Conf=0.
   Extracts structured entities from raw PDF text using Claude Sonnet 4.

2. llm_validate(): Anti false-positive gate when 50 <= Conf < 80.
   Asks the LLM whether a proposed SHIPTO makes sense given the PDF text.

Endpoint: databricks-claude-sonnet-4 (Databricks Foundation Model API)
"""

import json
import logging
import re
from typing import Optional

try:
    import mlflow.deployments
    _client = mlflow.deployments.get_deploy_client("databricks")
except Exception:
    _client = None

logger = logging.getLogger(__name__)

MODEL_ENDPOINT = "databricks-claude-sonnet-4"
FALLBACK_ENDPOINT = "databricks-meta-llama-3-3-70b-instruct"


def _call_llm(prompt: str, max_tokens: int = 400, endpoint: str = MODEL_ENDPOINT) -> Optional[str]:
    """Call the LLM endpoint and return the text response."""
    if _client is None:
        logger.warning("mlflow.deployments client not available")
        return None
    try:
        resp = _client.predict(
            endpoint=endpoint,
            inputs={
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": 0,
            },
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"LLM call failed ({endpoint}): {e}")
        # Try fallback
        if endpoint != FALLBACK_ENDPOINT:
            try:
                resp = _client.predict(
                    endpoint=FALLBACK_ENDPOINT,
                    inputs={
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": 0,
                    },
                )
                return resp["choices"][0]["message"]["content"].strip()
            except Exception as e2:
                logger.warning(f"LLM fallback also failed: {e2}")
        return None


def _parse_json(text: str) -> Optional[dict]:
    """Extract JSON from LLM response (handles ```json blocks)."""
    if not text:
        return None
    # Strip markdown code fences
    cleaned = re.sub(r"```json\s*", "", text)
    cleaned = re.sub(r"```\s*", "", cleaned)
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


# -------------------------------------------------------------------------
# 1. LLM EXTRACTION (fallback for Conf=0)
# -------------------------------------------------------------------------

EXTRACTION_PROMPT = """Tu es un extracteur de donnees de commandes B2B francaises.
Le texte suivant provient d'un PDF (possiblement OCR avec erreurs).

TEXTE DU PDF:
---
{text}
---

Extrais les informations suivantes. Si un champ est absent ou illisible, mets null.
ATTENTION:
- "Adresse de livraison" = adresse du DESTINATAIRE (pas l'expediteur Bosch/ELM LEBLANC)
- Si tu vois "Livrer a", "Ship to", "Destinataire" -> c'est l'adresse de livraison
- L'expediteur (Bosch Thermotechnologie, ELM LEBLANC, 124-126 rue de Stalingrad Drancy) n'est PAS le client
- Le numero de commande client (PO) est different du numero de commande SAP Bosch

Reponds UNIQUEMENT en JSON (pas de markdown, pas de ```):
{{"nom_client": "...", "adresse_livraison": {{"rue": "...", "code_postal": "...", "ville": "..."}}, "numero_commande": "...", "date_commande": "YYYY-MM-DD ou null", "date_livraison_souhaitee": "YYYY-MM-DD ou null", "tva": "...", "siren": "...", "numero_client": "..."}}"""


def llm_extract(text: str) -> Optional[dict]:
    """Extract structured entities from PDF text using LLM.

    Returns dict with keys: nom_client, adresse_livraison, numero_commande, tva, siren, numero_client
    or None if extraction fails.
    """
    if not text or len(text) < 30:
        return None

    # Truncate very long texts to stay within token limits
    truncated = text[:3000] if len(text) > 3000 else text
    prompt = EXTRACTION_PROMPT.format(text=truncated)

    raw = _call_llm(prompt, max_tokens=300)
    result = _parse_json(raw)

    if result and isinstance(result, dict):
        logger.info(f"LLM extraction: {result.get('nom_client', '?')} / {result.get('adresse_livraison', {})}")
        return result
    return None


# -------------------------------------------------------------------------
# 2. LLM VALIDATION (anti false-positive for 50 <= Conf < 80)
# -------------------------------------------------------------------------

VALIDATION_PROMPT = """Tu es un validateur de correspondance SHIPTO dans un contexte B2B francais.

TEXTE DU PDF:
---
{text}
---

SHIPTO PROPOSE:
- Code: {shipto_id}
- Nom: {shipto_name}
- Adresse: {shipto_street}, {shipto_postal} {shipto_city}
- SOLDTO (donneur d'ordre): {soldto_id}

QUESTION: Le SHIPTO propose correspond-il a l'adresse de LIVRAISON (destinataire) visible dans le PDF ?
Regles:
- L'expediteur (Bosch, ELM LEBLANC, Drancy) n'est PAS le destinataire
- Compare nom, ville et code postal du SHIPTO avec ce qui est dans le PDF
- Si le nom du client dans le PDF ressemble au nom du SHIPTO -> match probable
- Si le PDF ne contient pas assez d'info pour decider, reponds confiance=30

Reponds UNIQUEMENT en JSON (pas de markdown):
{{"match": true/false, "raison": "explication courte", "confiance": 0-100}}"""


def llm_validate(text: str, shipto_info: dict, soldto_id: str = "") -> Optional[dict]:
    """Validate a proposed SHIPTO match against PDF text.

    Args:
        text: Raw PDF text
        shipto_info: dict with keys id, name, street, postal, city
        soldto_id: The SOLDTO code

    Returns:
        dict with keys: match (bool), raison (str), confiance (int)
        or None if validation fails.
    """
    if not text or not shipto_info:
        return None

    truncated = text[:3000] if len(text) > 3000 else text
    prompt = VALIDATION_PROMPT.format(
        text=truncated,
        shipto_id=shipto_info.get("id", "?"),
        shipto_name=shipto_info.get("name", "?"),
        shipto_street=shipto_info.get("street", "?"),
        shipto_postal=shipto_info.get("postal", "?"),
        shipto_city=shipto_info.get("city", "?"),
        soldto_id=soldto_id,
    )

    raw = _call_llm(prompt, max_tokens=200)
    result = _parse_json(raw)

    if result and isinstance(result, dict) and "match" in result:
        logger.info(f"LLM validation: match={result['match']}, conf={result.get('confiance')}, raison={result.get('raison', '')[:50]}")
        return result
    return None


# -------------------------------------------------------------------------
# 3. RESOLVE WITH LLM (combines extraction + masterdata lookup)
# -------------------------------------------------------------------------

def llm_resolve(text: str, master_data: dict, pre_extracted: dict = None) -> dict:
    """Use LLM extraction to find SHIPTO when rules failed.

    Strategy:
    1. LLM extracts customer name, address, order number, VAT
    2. Match extracted fields against masterdata
    3. Return best SHIPTO candidate with confidence

    Args:
        pre_extracted: if llm_extract() was already called, pass the result to avoid a second call.
    """
    extracted = pre_extracted if pre_extracted else llm_extract(text)
    if not extracted:
        return {"resolved": False, "reason": "llm_extraction_failed"}

    from app.engines.cross_resolver import fold_text, _get_shiptos_for_soldto, _score_shipto_vs_text

    candidates = []

    # Try to find SOLDTO via customer number
    client_num = extracted.get("numero_client")
    if client_num:
        customers_by_id = master_data.get("customers_by_id", {})
        if client_num in customers_by_id:
            candidates.append((client_num, "llm_client_number"))

    # Try to find SOLDTO via VAT/SIREN
    tva = extracted.get("tva") or ""
    siren = extracted.get("siren") or ""
    customers_by_vat = master_data.get("customers_by_vat", {})
    for val in [tva, siren]:
        if val and len(val) >= 9:
            # Normalize: remove spaces, FR prefix
            normalized = re.sub(r"[\s.]", "", val).upper()
            if normalized.startswith("FR"):
                normalized = normalized[2:]
            for vat_key, cust_list in customers_by_vat.items():
                vat_clean = re.sub(r"[\s.]", "", vat_key).upper()
                if vat_clean.startswith("FR"):
                    vat_clean = vat_clean[2:]
                if normalized in vat_clean or vat_clean in normalized:
                    for c in cust_list:
                        candidates.append((c.get("id"), "llm_vat_match"))

    # Try to find SOLDTO via customer name
    nom = extracted.get("nom_client") or ""
    if nom and len(nom) >= 5:
        nom_folded = fold_text(nom)
        customers = master_data.get("customers", [])
        for c in customers:
            cname = c.get("name", "")
            if not cname or len(cname) < 5:
                continue
            cname_folded = fold_text(cname)
            # Skip Bosch-related names
            if any(x in cname_folded for x in ("bosch", "leblanc", "elm")):
                continue
            # Check similarity (substring match)
            if nom_folded in cname_folded or cname_folded in nom_folded:
                candidates.append((c.get("id"), "llm_name_match"))

    # Try to find SOLDTO via order number (BSTNK)
    order_num = extracted.get("numero_commande") or ""
    if order_num and len(order_num) >= 4:
        salesorders_by_bstnk = master_data.get("salesorders_by_bstnk", {})
        order_clean = order_num.strip()
        if order_clean in salesorders_by_bstnk:
            so = salesorders_by_bstnk[order_clean]
            kunnr = so.get("KUNNR") or so.get("kunnr", "")
            if kunnr:
                candidates.append((kunnr, "llm_order_bstnk"))

    if not candidates:
        return {"resolved": False, "reason": "llm_no_candidate", "extracted": extracted}

    # Score each candidate's SHIPTOs against extracted address
    addr = extracted.get("adresse_livraison") or {}
    detected_address = {
        "street": addr.get("rue", ""),
        "postal": addr.get("code_postal", ""),
        "city": addr.get("ville", ""),
    }

    best_score = -1
    best_soldto = None
    best_shipto = None
    best_path = None

    seen_soldtos = set()
    for soldto_id, path in candidates:
        if not soldto_id or soldto_id in seen_soldtos:
            continue
        seen_soldtos.add(soldto_id)

        shiptos = _get_shiptos_for_soldto(soldto_id, master_data)
        if not shiptos:
            # SOLDTO without SHIPTO -> use SOLDTO itself
            customers_by_id = master_data.get("customers_by_id", {})
            cust = customers_by_id.get(soldto_id)
            if cust:
                score = _score_shipto_vs_text(cust, text, detected_address)
                if score > best_score:
                    best_score = score
                    best_soldto = soldto_id
                    best_shipto = soldto_id
                    best_path = path
        else:
            for sh in shiptos:
                score = _score_shipto_vs_text(sh, text, detected_address)
                if score > best_score:
                    best_score = score
                    best_soldto = soldto_id
                    best_shipto = sh.get("id", soldto_id)
                    best_path = path

    if best_soldto:
        # Confidence based on score
        if best_score >= 80:
            confidence = 95
        elif best_score >= 50:
            confidence = 75
        elif best_score >= 20:
            confidence = 50
        else:
            confidence = 30

        return {
            "resolved": True,
            "soldto": best_soldto,
            "shipto": best_shipto,
            "confidence": confidence,
            "path": f"llm:{best_path}",
            "score": best_score,
            "extracted": extracted,
        }

    return {"resolved": False, "reason": "llm_no_match", "extracted": extracted}
