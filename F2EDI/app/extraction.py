from __future__ import annotations

import json
import re
import time

from app.amounts import extract_document_totals, rank_amounts_by_context
from app.document import build_cross_validation, build_debug_summary
from app.engines.customer_order import CustomerOrderNumberEngine
from app.engines.delivery_address import DeliveryAddressEngine
from app.engines.order_lines import OrderLinesEngine
from app.engines.shipto_matching import ShipToMatchingEngine
from app.engines.tax_identification import TaxIdentificationEngine
from app.engines.cross_resolver import cross_resolve
from app.engines.llm_resolver import llm_resolve, llm_validate
from app.engines.llm_orderlines import llm_extract_orderlines
from app.engines.rejection_engine import check_rejections, rejection_summary
from app.edifact_generator import structured_to_order, build_orders_d96a, EdifactBuildError
from app.masterdata import get_master_data, validate_order_number
from app.text_utils import compact_text, first_value, fold_text, unique


def candidate_lines(text: str, keywords: list[str], limit: int = 8) -> list[str]:
    matches = []
    for line in text.splitlines():
        folded = fold_text(line)
        if any(keyword in folded for keyword in keywords):
            matches.append(line)
    return unique(matches, limit=limit)



def _normalize_for_compare(s: str) -> str:
    """Normalize string for robust comparison: lowercase, normalize quotes/dashes/spaces."""
    s = s.upper()
    # Normalize all types of apostrophes and quotes
    s = s.replace("\u2019", "'").replace("\u2018", "'").replace("\u201C", '"').replace("\u201D", '"')
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = s.replace("\xa0", " ")
    s = " ".join(s.split())
    return s


def _llm_disambiguate_with_explanation(
    text: str, candidates: list, soldto_id: str, agency_code: str | None
) -> dict | None:
    """Ask LLM to pick the correct SHIPTO from candidates and EXPLAIN its reasoning.
    
    Returns: {"chosen": partner_dict, "explanation": str} or None if uncertain.
    The LLM MUST explain HOW it decided. If it can't explain clearly → returns None → REJECT.
    """
    try:
        from app.engines.llm_resolver import _call_llm
        import json as _json

        candidates_desc = "\n".join([
            f"  {i+1}. ID={c.get('id','')} | Nom: {c.get('name','')} | "
            f"Rue: {c.get('street','')} | CP: {c.get('postal','')} | Ville: {c.get('city','')}"
            for i, c in enumerate(candidates)
        ])

        agency_hint = ""
        if agency_code:
            agency_hint = f"\nINDICE IMPORTANT: Le document contient le code agence '{agency_code}' (après le N° de commande)."

        prompt = f"""Tu es un expert en résolution d'adresses de livraison sur des bons de commande B2B.

DOCUMENT (texte intégral page 1):
{text[:2500]}
{agency_hint}

CONTEXTE: Le client SOLDTO est {soldto_id}. Il a plusieurs adresses de livraison (SHIPTO) possibles.
SHIPTO = SOLDTO (siège social). Il faut trouver la VRAIE adresse de LIVRAISON.

CANDIDATS SHIPTO:
{candidates_desc}

MISSION:
1. Identifie quelle adresse candidate est l'ADRESSE DE LIVRAISON dans ce document
2. EXPLIQUE comment tu as trouvé (quels éléments du texte t'ont permis de conclure)
3. Si tu n'es PAS SÛR à 100% → réponds AUCUN

INDICES À CHERCHER:
- Section "Adresse de livraison" / "Livrer à" / "Ship to"
- Code agence entre parenthèses dans le nom du partenaire (ex: STQ, VMC, HAU)
- Code postal et ville dans la zone de livraison (pas facturation)
- Rue correspondante

REPONSE AU FORMAT JSON STRICT:
{{"choix": <numéro 1-N ou 0 si aucun>, "explication": "<comment tu as identifié cette adresse>"}}

Si tu ne peux pas décider avec certitude, réponds: {{"choix": 0, "explication": "trop ambigu"}}"""

        response = _call_llm(prompt, max_tokens=200)
        # Parse JSON response
        response = response.strip()
        # Handle markdown code blocks
        if response.startswith("```"):
            response = response.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        
        result = _json.loads(response)
        choix = result.get("choix", 0)
        explanation = result.get("explication", "")
        
        if choix == 0 or not explanation:
            return None
        
        idx = choix - 1
        if 0 <= idx < len(candidates):
            return {"chosen": candidates[idx], "explanation": explanation}
        return None
    except Exception as e:
        return None  # LLM failure = doubt = no disambiguation → rejection


def _llm_validate_final_shipto(text: str, matched_address: dict) -> bool | None:
    """Ask LLM if the matched SHIPTO address is consistent with the document.
    Returns True (confirmed), False (contradicted), None (uncertain).
    """
    try:
        from app.engines.llm_resolver import _call_llm
        import json as _json

        addr = f"{matched_address.get('Rue', '')}, {matched_address.get('Code postal', '')} {matched_address.get('Ville', '')}"
        prompt = f"""Tu es un expert en verification d'adresses de livraison.

DOCUMENT (extrait page 1):
{text[:2000]}

ADRESSE SHIPTO MATCHEE: {addr}

QUESTION: Cette adresse correspond-elle a l'adresse de LIVRAISON indiquee dans le document ?
- Cherche la section "Adresse de livraison" / "Livrer a" / "Ship to"
- Compare le code postal et la ville avec ce qui est ecrit dans cette section

REPONSE: "OUI" si l'adresse correspond, "NON" si le document indique une AUTRE adresse de livraison, "INCERTAIN" si tu ne peux pas determiner.
Reponds en un seul mot:"""

        response = _call_llm(prompt, max_tokens=10)
        answer = response.strip().upper()
        if "OUI" in answer:
            return True
        elif "NON" in answer:
            return False
        return None
    except Exception:
        return None


def extract_structured_fields(
    text: str,
    fields: dict,
    filename: str | None = None,
    layout_analysis: dict | None = None,
    extraction_context: dict | None = None,
    layout: dict | None = None,
) -> dict:
    context = extraction_context or {}
    compact = compact_text(text)
    folded = fold_text(compact)
    header = re.split(r"\b(?:Merci de livrer|Montant HT|Prix net|Total HT)\b", compact, maxsplit=1)[0]
    tax_identification = fields.get("tax_identification") or TaxIdentificationEngine().extract(text)
    vat_numbers = tax_identification.get("vat_numbers") or []

    reference_codes = [
        code
        for code in re.findall(r"\b[A-Z]{2,}\d{4}[A-Z0-9]{4,}\b", header)
        if code.upper() not in {item.upper().replace(" ", "") for item in vat_numbers}
    ]
    supplier_code = first_value(re.findall(r"Code fournisseur\s*:?\s*(\d+)", compact, flags=re.IGNORECASE))

    totals = extract_document_totals(text)
    ranked_amounts = rank_amounts_by_context(text, fields.get("amounts", []))
    payment = first_value(re.findall(r"(Virement\s+[^.]+?(?:le\s+\d{1,2})?)", compact, flags=re.IGNORECASE))
    delivery_mode = first_value(re.findall(r"Mode livraison\s*:?\s*([A-Za-z][A-Za-z -]{2,30})", compact, flags=re.IGNORECASE))
    if delivery_mode and "virement" in fold_text(delivery_mode):
        delivery_mode = "Standard" if "standard" in folded else None

    companies = unique(
        re.findall(r"\b(?:BOSCH PRODUITS FINIS|ISERBA|BAV|[A-Z][A-Z0-9&' -]{3,})\b", header),
        limit=12,
    )
    document_type = "Bon de commande" if "bon de commande" in folded else None
    order_engine_result = fields.get("customer_order_number") or CustomerOrderNumberEngine().extract(text, filename)
    order_number = context.get("order_number") or order_engine_result.get("order_number")
    delivery_engine = DeliveryAddressEngine()
    if layout_analysis is None:
        layout_analysis = delivery_engine.analyze_layout(layout)
    shipto_result = ShipToMatchingEngine().resolve_best(
        text=text,
        fields=fields,
        filename=filename,
        layout=layout,
        layout_analysis=layout_analysis,
        order_number=order_number,
        known_soldto_id=context.get("known_soldto_id"),
    )
    delivery_address = shipto_result["detected_address"]
    master_delivery_address = shipto_result["shipto"]

    # Cross-resolution: if primary matching failed, try alternate paths
    primary_confidence = master_delivery_address.get("Confiance", 0)
    if (not primary_confidence or primary_confidence == 0) and tax_identification:
        cross_resolution = cross_resolve(
            text=text,
            tax_result=tax_identification,
            order_result=order_engine_result,
            detected_address=delivery_address,
            validated_result=master_delivery_address,
        )
        if cross_resolution.get("resolved"):
            shipto_entry = cross_resolution["shipto"]
            master_delivery_address = {
                "Statut": cross_resolution["statut"],
                "Confiance": cross_resolution["confidence"],
                "Raison": f"cross_resolve:{cross_resolution['path']}",
                "SOLDTO": cross_resolution["soldto"],
                "SHIPTO": shipto_entry.get("id", cross_resolution["soldto"]),
                "Nom": shipto_entry.get("name", ""),
                "Rue": shipto_entry.get("street", ""),
                "Code postal": shipto_entry.get("postal", ""),
                "Ville": shipto_entry.get("city", ""),
                "Pays": shipto_entry.get("country", "FR"),
                "Adresse complete": "\n".join(filter(None, [
                    shipto_entry.get("name", ""),
                    shipto_entry.get("street", ""),
                    f"{shipto_entry.get('postal', '')} {shipto_entry.get('city', '')}".strip(),
                    shipto_entry.get("country", ""),
                ])),
                "Cross resolution": cross_resolution["path"],
                "Cross score": cross_resolution.get("score", 0),
                "Candidats SHIPTO": cross_resolution.get("candidates_count", 0),
                "Guidage masterdata": "oui",
            }

    # LLM Layer: Systematic extraction (Sonnet 4) + Fallback + Validation
    current_confidence = master_delivery_address.get("Confiance", 0)

    # --- LLM EXTRACTION SYSTÉMATIQUE (Sonnet 4 pour N° commande sur tous les PDFs) ---
    llm_extracted = None
    try:
        from app.engines.llm_resolver import llm_extract
        _raw = llm_extract(text)
        if isinstance(_raw, dict):
            llm_extracted = _raw
        elif isinstance(_raw, list) and _raw and isinstance(_raw[0], dict):
            llm_extracted = _raw[0]
    except Exception:
        pass

    # --- LLM FALLBACK SHIPTO: if still Conf=0 after rules + cross-resolution ---
    if not current_confidence or current_confidence == 0:
        try:
            llm_result = llm_resolve(text, get_master_data(), pre_extracted=llm_extracted)
            if llm_result.get("resolved"):
                from app.engines.cross_resolver import _get_shiptos_for_soldto
                md = get_master_data()
                # Get SHIPTO details
                shipto_id = llm_result["shipto"]
                soldto_resolved = llm_result["soldto"]
                shiptos = _get_shiptos_for_soldto(soldto_resolved, md)
                shipto_entry = next((s for s in shiptos if s.get("id") == shipto_id), None)
                if not shipto_entry:
                    # SHIPTO = SOLDTO case
                    customers_by_id = md.get("customers_by_id", {})
                    shipto_entry = customers_by_id.get(shipto_id, {})

                master_delivery_address = {
                    "Statut": f"LLM resolution ({llm_result['path']})",
                    "Confiance": llm_result["confidence"],
                    "Raison": f"llm_resolve:{llm_result['path']}",
                    "SOLDTO": soldto_resolved,
                    "SHIPTO": shipto_id,
                    "Nom": shipto_entry.get("name", ""),
                    "Rue": shipto_entry.get("street", ""),
                    "Code postal": shipto_entry.get("postal", ""),
                    "Ville": shipto_entry.get("city", ""),
                    "Pays": shipto_entry.get("country", "FR"),
                    "Adresse complete": "\n".join(filter(None, [
                        shipto_entry.get("name", ""),
                        shipto_entry.get("street", ""),
                        f"{shipto_entry.get('postal', '')} {shipto_entry.get('city', '')}".strip(),
                        shipto_entry.get("country", ""),
                    ])),
                    "Cross resolution": llm_result["path"],
                    "Cross score": llm_result.get("score", 0),
                    "LLM extracted": llm_result.get("extracted", {}),
                    "Guidage masterdata": "oui",
                }
                current_confidence = llm_result["confidence"]
        except Exception as e:
            pass  # LLM failure is non-blocking

    # --- LLM VALIDATOR: only for weak cross-resolution paths (name_match, order_bstnk) ---
    # Do NOT validate strong signals (vat_siren_scored, client_number, vat_siren)
    cross_path = master_delivery_address.get("Cross resolution", "")
    weak_paths = ("name_match", "order_bstnk", "name_match_scored")
    is_weak_cross = any(wp in cross_path for wp in weak_paths) if cross_path else False
    if 50 <= current_confidence < 80 and is_weak_cross:
        try:
            shipto_info = {
                "id": master_delivery_address.get("SHIPTO", ""),
                "name": master_delivery_address.get("Nom", ""),
                "street": master_delivery_address.get("Rue", ""),
                "postal": master_delivery_address.get("Code postal", ""),
                "city": master_delivery_address.get("Ville", ""),
            }
            soldto_for_valid = master_delivery_address.get("SOLDTO", "")
            validation = llm_validate(text, shipto_info, soldto_for_valid)
            if validation:
                if validation.get("match") is True and validation.get("confiance", 0) >= 70:
                    # LLM confirms: boost confidence
                    master_delivery_address["Confiance"] = max(current_confidence, 75)
                    master_delivery_address["LLM validation"] = f"confirmed ({validation.get('confiance')})"
                elif validation.get("match") is False and validation.get("confiance", 0) >= 70:
                    # LLM rejects: downgrade to 0
                    master_delivery_address["Confiance"] = 0
                    master_delivery_address["Statut"] = "Rejet LLM validation"
                    master_delivery_address["LLM validation"] = f"rejected: {validation.get('raison', '')}"
                else:
                    master_delivery_address["LLM validation"] = f"uncertain ({validation.get('confiance', '?')})"
        except Exception as e:
            pass  # LLM failure is non-blocking

    # --- LLM ORDER NUMBER: override regex if LLM extracted a clean order number ---
    llm_order_number = None
    if llm_extracted and llm_extracted.get("numero_commande"):
        llm_cmd = str(llm_extracted["numero_commande"]).strip()
        # Accept LLM order number if it's not null/empty and not a date
        if llm_cmd and llm_cmd.lower() not in ("null", "none", ""):
            if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", llm_cmd) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", llm_cmd):
                llm_order_number = llm_cmd

    # Use LLM order number as primary, regex as fallback
    final_order_number = llm_order_number or order_number

    # --- LLM ORDER LINES: extract article lines with Sonnet 4 ---
    order_lines = []
    try:
        order_lines = llm_extract_orderlines(text)
    except Exception:
        pass  # Non-blocking

    soldto_id = context.get("known_soldto_id") or master_delivery_address.get("SOLDTO")
    order_validation = validate_order_number(get_master_data(), final_order_number, soldto_id)
    cross_validation = build_cross_validation(order_validation, master_delivery_address)

    resolved_soldto = master_delivery_address.get("SOLDTO", "")
    resolved_shipto = master_delivery_address.get("SHIPTO", "")

    # --- MEMO + LLM FALLBACK: when SOLDTO not identified by rules ---
    if not resolved_soldto or resolved_soldto == "":
        try:
            from app.memo import build_memo_context_for_llm, search_memo
            from app.engines.llm_resolver import _call_llm
            import json as _json_memo
            
            # Try to find client in memo by name/text patterns
            memo_hit = ""
            # Extract potential client names from text (first lines usually have the client)
            _first_lines = text[:500]
            for _candidate_name in ["WENDEL", "SALICA", "ANDRETY", "ISERBA", "GAZ SERVICE"]:
                if _candidate_name in _first_lines.upper():
                    memo_hit = search_memo(_candidate_name)
                    break
            
            if not memo_hit:
                # Generic search by postal codes in text
                import re as _re_memo
                _postals = _re_memo.findall(r"\b(\d{5})\b", _first_lines)
                for _p in _postals[:3]:
                    _hit = search_memo(_p)
                    if _hit:
                        memo_hit = _hit
                        break
            
            if memo_hit:
                # Ask LLM to resolve using memo context
                _memo_prompt = f"""Tu es un expert en identification de clients pour des commandes B2B.

CONTEXTE MEMO (cas connus):
{memo_hit}

DOCUMENT (debut):
{text[:2000]}

QUESTION: Quel est le SOLDTO (code client SAP) pour cette commande?
Cherche dans le memo si ce client y est reference.

Reponds en JSON: {{"soldto": "XXXXXXXX", "raison": "explication courte"}}
Si tu ne peux pas determiner: {{"soldto": "", "raison": "..."}}"""
                
                _memo_response = _call_llm(_memo_prompt, max_tokens=100)
                _memo_json = _re_memo.search(r"\{[^}]+\}", _memo_response)
                if _memo_json:
                    _memo_data = _json_memo.loads(_memo_json.group())
                    _memo_soldto = _memo_data.get("soldto", "")
                    if _memo_soldto and len(_memo_soldto) >= 7:
                        # Verify SOLDTO exists in masterdata
                        _md = get_master_data()
                        if _memo_soldto in (_md.get("customers_by_id", {}) or {}):
                            resolved_soldto = _memo_soldto
                            master_delivery_address["SOLDTO"] = _memo_soldto
                            master_delivery_address["SHIPTO"] = _memo_soldto
                            master_delivery_address["Raison"] = f"memo_llm: {_memo_data.get('raison', '')}"
                            master_delivery_address["Confiance"] = 0  # Will be set by scoring
                        elif _md.get("partners_by_soldto", {}).get(_memo_soldto):
                            resolved_soldto = _memo_soldto
                            master_delivery_address["SOLDTO"] = _memo_soldto
                            master_delivery_address["SHIPTO"] = _memo_soldto
                            master_delivery_address["Raison"] = f"memo_llm: {_memo_data.get('raison', '')}"
                            master_delivery_address["Confiance"] = 0
        except Exception:
            pass  # Non-blocking: if memo fails, continue with normal flow

# --- SHIPTO RESOLUTION VIA SCORING ENGINE ---
    # Replaces the old Level 0/1/2 cascade with evidence-based scoring.
    # Each SHIPTO candidate gets points based on evidence found in the PDF.
    # LLM is only used as fallback on top 3 candidates if score < 95 or gap < 15.
    resolved_soldto = master_delivery_address.get("SOLDTO", "")
    resolved_shipto = master_delivery_address.get("SHIPTO", "")

    # Always run scoring engine when SOLDTO has multiple SHIPTOs
    # The scoring engine replaces the old masterdata resolution with evidence-based scoring
    if resolved_soldto:
        from app.engines.shipto_scoring import resolve_shipto_with_scoring
        md = get_master_data()
        partners = md.get("partners_by_soldto", {}).get(resolved_soldto, [])

        if len(partners) > 1:
            # Run the scoring engine
            scoring_result = resolve_shipto_with_scoring(
                text=text,
                soldto_id=resolved_soldto,
                masterdata=md,
                soldto_confidence=master_delivery_address.get("Confiance", 80),
                use_llm_fallback=True,
            )

            if scoring_result.best_candidate and scoring_result.shipto_confidence > 0:
                best = scoring_result.best_candidate
                # Update master_delivery_address with the scoring result
                master_delivery_address["SHIPTO"] = best.shipto_id
                master_delivery_address["Nom"] = best.name
                master_delivery_address["Rue"] = best.street
                master_delivery_address["Code postal"] = best.postal
                master_delivery_address["Ville"] = best.city
                master_delivery_address["Confiance"] = scoring_result.shipto_confidence
                master_delivery_address["Disambiguation"] = (
                    f"SCORING:{best.score}pts "
                    f"{'+'.join(scoring_result.matched_by[:3])}"
                    f"→{best.shipto_id} {best.city}"
                )
                master_delivery_address["Disambiguation_explanation"] = scoring_result.explanation
                master_delivery_address["reason_codes"] = scoring_result.reason_codes
                master_delivery_address["matched_by"] = scoring_result.matched_by
                master_delivery_address["shipto_score"] = best.score
                master_delivery_address["scoring_decision"] = scoring_result.decision

            elif scoring_result.error:
                # Scoring failed with error → keep SOLDTO as SHIPTO, mark for review
                master_delivery_address["Confiance"] = 0
                master_delivery_address["Statut"] = f"ERREUR SCORING: {scoring_result.error}"
                master_delivery_address["reason_codes"] = scoring_result.reason_codes
                master_delivery_address["scoring_decision"] = "REJECTED"

            else:
                # No valid candidate → mark confidence 0
                master_delivery_address["Confiance"] = 0
                master_delivery_address["Statut"] = "Aucun SHIPTO ne correspond aux preuves du document"
                master_delivery_address["reason_codes"] = scoring_result.reason_codes
                master_delivery_address["scoring_decision"] = scoring_result.decision or "REJECTED"

        elif len(partners) == 1:
            # Single SHIPTO: use it but validate via post-check
            single = partners[0]
            master_delivery_address["SHIPTO"] = single["id"]
            master_delivery_address["Nom"] = single.get("name", "")
            master_delivery_address["Rue"] = single.get("street", "")
            master_delivery_address["Code postal"] = single.get("postal", "")
            master_delivery_address["Ville"] = single.get("city", "")
            # Post-validate: is the postal in the text?
            if single.get("postal") and single["postal"] in text:
                master_delivery_address["Confiance"] = 100
                master_delivery_address["Disambiguation"] = f"UNIQUE_SHIPTO:{single['id']} (postal confirmed)"
                master_delivery_address["reason_codes"] = ["SINGLE_SHIPTO", "POSTAL_CONFIRMED"]
            else:
                master_delivery_address["Confiance"] = 80
                master_delivery_address["Disambiguation"] = f"UNIQUE_SHIPTO:{single['id']}"
                master_delivery_address["reason_codes"] = ["SINGLE_SHIPTO"]

        # --- REJECTION ENGINE: check all 9 Esker rejection rules ---
    rejection_input = {
        "document": {
            "Type": document_type,
            "Numero de commande": final_order_number,
        },
        "adresses": {
            "Adresse de livraison validee": master_delivery_address,
        },
        "lignes_commande": {
            "lignes": order_lines,
            "nb_lignes": len(order_lines),
        },
    }
    rejections = check_rejections(rejection_input, master_data=get_master_data())
    rejection_result = rejection_summary(rejections)

    # --- SCORING DECISION OVERRIDE ---
    # The scoring engine decision is AUTHORITATIVE for SHIPTO confidence.
    # If scoring says REJECTED, the final decision CANNOT be ACCEPTED.
    _scoring_dec = master_delivery_address.get("scoring_decision", "")
    _scoring_conf = master_delivery_address.get("Confiance", 100)
    
    # Confidence = 0 means post-validation FAILED → always REJECTED
    if _scoring_conf == 0 and rejection_result.get("decision") in ("ACCEPTED", "REVIEW"):
        rejection_result["decision"] = "REJECTED"
        rejection_result["primary_reason"] = "CONFIDENCE_ZERO"
        rejection_result.setdefault("rejections", []).append({
            "code": "CONFIDENCE_ZERO",
            "message": "Confiance 0%: aucune preuve documentaire ne confirme le SHIPTO",
            "severity": "blocking",
        })
    elif _scoring_dec == "REJECTED" and rejection_result.get("decision") == "ACCEPTED":
        rejection_result["decision"] = "REJECTED"
        rejection_result["primary_reason"] = "SCORING_REJECTED"
        rejection_result.setdefault("rejections", []).append({
            "code": "SCORING_REJECTED",
            "message": f"Scoring engine rejected: confidence {_scoring_conf}%, insufficient evidence",
            "severity": "blocking",
        })
    elif _scoring_dec == "REJECTED" and rejection_result.get("decision") == "REVIEW":
        rejection_result["decision"] = "REJECTED"
    elif _scoring_dec == "REVIEW" and rejection_result.get("decision") == "ACCEPTED":
        rejection_result["decision"] = "REVIEW"
        rejection_result["primary_reason"] = "SCORING_REVIEW"
        rejection_result.setdefault("rejections", []).append({
            "code": "SCORING_REVIEW",
            "message": f"Scoring engine requires review: confidence {_scoring_conf}%",
            "severity": "warning",
        })
    # Also: if confidence < 70 → never ACCEPTED
    if _scoring_conf < 70 and _scoring_conf > 0 and rejection_result.get("decision") == "ACCEPTED":
        rejection_result["decision"] = "REVIEW"
        rejection_result.setdefault("rejections", []).append({
            "code": "LOW_CONFIDENCE",
            "message": f"Confidence {_scoring_conf}% too low for automatic acceptance",
            "severity": "warning",
        })

        # --- EDIFACT D96A: generate message if not blocked ---
    edifact_message = None
    edifact_errors = None
    edifact_warnings = []
    edifact_generated = False
    if rejection_result.get("decision") != "REJECTED":
        try:
            edifact_input = {
                "document": {
                    "Numero de commande": final_order_number,
                    "Date commande LLM": llm_extracted.get("date_commande") if llm_extracted else None,
                    "Date document": first_value(fields.get("dates", [])),
                    "Date livraison souhaitee": llm_extracted.get("date_livraison_souhaitee") if llm_extracted else None,
                },
                "adresses": {
                    "Adresse de livraison validee": master_delivery_address,
                },
                "lignes_commande": {
                    "lignes": order_lines,
                },
            }
            order_obj, build_errors = structured_to_order(edifact_input)
            if order_obj is None:
                edifact_errors = build_errors
            else:
                interchange_ref = f"LA{final_order_number or 'X'}".replace("/", "")[:14]
                edifact_message, edifact_warnings = build_orders_d96a(order=order_obj, interchange_ref=interchange_ref)
                edifact_generated = True
        except EdifactBuildError as e:
            edifact_errors = e.errors
        except Exception as e:
            edifact_errors = [str(e)]

    return {
        "document": {
            "Type": document_type,
            "Numero de commande": final_order_number,
            "Numero commande LLM": llm_order_number,
            "Numero commande regex": order_number,
            "CustomerOrderNumberEngine": order_engine_result,
            "Commande masterdata": order_validation,
            "Reference": first_value(reference_codes),
            "Date document": first_value(fields.get("dates", [])),
            "Date commande LLM": llm_extracted.get("date_commande") if llm_extracted else None,
            "Date livraison souhaitee": llm_extracted.get("date_livraison_souhaitee") if llm_extracted else None,
            "Code fournisseur": supplier_code,
            "TVA intracommunautaire": first_value(vat_numbers),
            "Identification fiscale": tax_identification,
        },
        "adresses": {
            "Adresse de livraison validee": master_delivery_address,
            "Adresse de livraison detectee": delivery_address,
        },
        "lignes_commande": {
            "lignes": order_lines,
            "nb_lignes": len(order_lines),
            "total_lignes_ht": round(sum(l.get("montant_ligne_ht") or 0 for l in order_lines), 2) if order_lines else None,
        },
        "rejets": rejection_result,
        "edifact": {
            "generated": edifact_generated,
            "message": edifact_message,
            "warnings": edifact_warnings if edifact_generated else [],
            "errors": edifact_errors,
        },
        "montants": {
            "Total HT": totals["Total HT"],
            "Total TTC": totals["Total TTC"],
            "Montants detectes": fields.get("amounts", []),
            "Montants priorises": ranked_amounts,
        },
        "conditions": {
            "Mode livraison": delivery_mode,
            "Condition paiement": payment,
        },
        "contacts": {
            "Emails": fields.get("emails", []),
            "Telephones": fields.get("phones", []),
        },
        "parties": {
            "Societes detectees": companies,
            "Client candidates": fields.get("client_candidates", []),
            "Fournisseur candidates": fields.get("supplier_candidates", []),
        },
        "identifiants": {
            "SIRET": tax_identification.get("siret") or fields.get("siret", []),
            "SIREN": tax_identification.get("siren") or fields.get("siren", []),
            "SIREN valide": tax_identification.get("valid_siren", []),
            "TVA candidates": tax_identification.get("vat_candidates", []),
            "TVA rejetees": tax_identification.get("rejected_vat_candidates", []),
            "TVA attendue depuis SIREN": tax_identification.get("expected_vat_from_siren", []),
            "IBAN": fields.get("iban", []),
        },
        "line_items": OrderLinesEngine().extract(text, layout=layout)["lines"],
        "validation": cross_validation,
    }


def extract_candidate_fields(
    text: str,
    instruction: str,
    filename: str | None = None,
    layout: dict | None = None,
    extraction_context: dict | None = None,
) -> dict:
    amount_pattern = r"(?<!\w)(?:(?:\d{1,3}(?:[ .]\d{3})*|\d+),\d{2}\s?(?:EUR|E|euros?)?|\d+\.\d{2}\s?€)(?!\w)"
    date_pattern = r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"
    phone_pattern = r"\b(?:0\d(?:[\s.-]?\d{2}){4}|(?:(?:\+|00)33\s?)[1-9](?:[\s.-]?\d{2}){4})\b"

    tax_identification = TaxIdentificationEngine().extract(text)
    customer_order_number = CustomerOrderNumberEngine().extract(text, filename)
    fields = {
        "requested": instruction,
        "emails": unique(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)),
        "phones": unique(re.findall(phone_pattern, text)),
        "dates": unique(re.findall(date_pattern, text)),
        "amounts": unique(re.findall(amount_pattern, text), limit=30),
        "total_candidates": candidate_lines(
            text,
            ["total ttc", "ttc", "net a payer", "montant total", "total a payer", "total due"],
        ),
        "document_number_candidates": candidate_lines(
            text,
            ["facture", "invoice", "document", "commande", "devis", "reference", "ref "],
        ),
        "client_candidates": candidate_lines(
            text,
            ["client", "facture a", "bill to", "destinataire", "acheteur", "customer"],
        ),
        "supplier_candidates": candidate_lines(
            text,
            ["fournisseur", "vendeur", "seller", "emetteur", "societe", "supplier"],
        ),
        "siret": tax_identification.get("siret", []),
        "siren": tax_identification.get("siren", []),
        "vat_numbers": tax_identification.get("vat_numbers", []),
        "vat_candidates": tax_identification.get("vat_candidates", []),
        "tax_identification": tax_identification,
        "customer_order_number": customer_order_number,
        "iban": unique(re.findall(r"\b[A-Z]{2}\d{2}(?:\s?[A-Z0-9]){11,30}\b", text, flags=re.IGNORECASE)),
    }
    layout_analysis = DeliveryAddressEngine().analyze_layout(layout)
    if layout_analysis.get("address_candidates") or layout_analysis.get("anchor_summaries"):
        fields["layout_analysis"] = {
            "candidate_summaries": layout_analysis.get("candidate_summaries", []),
            "anchor_summaries": layout_analysis.get("anchor_summaries", []),
        }
    fields["structured"] = extract_structured_fields(
        text, fields, filename, layout_analysis, extraction_context, layout
    )
    return fields


def update_extraction_context_from_structured(context: dict, structured: dict) -> None:
    document = structured.get("document", {})
    validated = structured.get("adresses", {}).get("Adresse de livraison validee", {})
    order_number = document.get("Numero de commande")
    if order_number and not context.get("order_number"):
        context["order_number"] = order_number
    soldto = validated.get("SOLDTO")
    if soldto:
        context["known_soldto_id"] = soldto


def build_text_extraction_result(
    page: int,
    text: str,
    source: str,
    instruction: str,
    filename: str | None = None,
    layout: dict | None = None,
    engine_name: str = "text_ocr",
    extraction_context: dict | None = None,
    include_debug: bool = False,
) -> dict:
    started = time.perf_counter()
    context = extraction_context if extraction_context is not None else {}
    fields = extract_candidate_fields(text, instruction, filename, layout, context)
    structured = fields.get("structured", {})
    update_extraction_context_from_structured(context, structured)
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    answer = json.dumps(
        {
            "source": source,
            "fields": fields,
            "text_excerpt": compact_text(text)[:4000],
        },
        ensure_ascii=False,
        indent=2,
    )
    result = {
        "page": page,
        "engine": engine_name,
        "device": "cpu",
        "generation_mode": source,
        "prompt": instruction,
        "answer": answer,
        "fields": fields,
        "raw_text": text,
        "boxes": [],
        "points": [],
        "timings_ms": {"extraction_total": elapsed_ms},
    }
    if include_debug:
        result["debug"] = build_debug_summary(structured)
    return result
