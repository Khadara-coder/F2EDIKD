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
            import re as _re
            if not _re.fullmatch(r"\d{2}/\d{2}/\d{4}", llm_cmd) and not _re.fullmatch(r"\d{4}-\d{2}-\d{2}", llm_cmd):
                llm_order_number = llm_cmd

    # Use LLM order number as primary, regex as fallback
    final_order_number = llm_order_number or order_number

    # --- LLM ORDER LINES: extract article lines with Sonnet 4 ---
    order_lines = []
    try:
        order_lines = llm_extract_orderlines(text)
    except Exception:
        pass  # Non-blocking

    # --- SHIPTO RESOLUTION VIA SCORING ENGINE ---
    # Replaces the old Level 0/1/2 cascade with evidence-based scoring.
    # Each SHIPTO candidate gets points based on evidence found in the PDF.
    # LLM is only used as fallback on top 3 candidates if score < 95 or gap < 15.
    resolved_soldto = master_delivery_address.get("SOLDTO", "")

    # Always run scoring engine when SOLDTO has multiple SHIPTOs
    if resolved_soldto:
        try:
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
                    master_delivery_address["SHIPTO"] = best.shipto_id
                    master_delivery_address["Nom"] = best.name
                    master_delivery_address["Rue"] = best.street
                    master_delivery_address["Code postal"] = best.postal
                    master_delivery_address["Ville"] = best.city
                    master_delivery_address["Confiance"] = scoring_result.shipto_confidence
                    master_delivery_address["Disambiguation"] = (
                        f"SCORING:{best.score}pts "
                        f"{'+'.join(scoring_result.matched_by[:3])}"
                        f"\u2192{best.shipto_id} {best.city}"
                    )
                    master_delivery_address["Disambiguation_explanation"] = scoring_result.explanation
                    master_delivery_address["reason_codes"] = scoring_result.reason_codes
                    master_delivery_address["matched_by"] = scoring_result.matched_by
                    master_delivery_address["shipto_score"] = best.score
                    master_delivery_address["scoring_decision"] = scoring_result.decision

                elif scoring_result.error:
                    master_delivery_address["Confiance"] = 0
                    master_delivery_address["Statut"] = f"ERREUR SCORING: {scoring_result.error}"
                    master_delivery_address["reason_codes"] = scoring_result.reason_codes
                    master_delivery_address["scoring_decision"] = "REJECTED"

                else:
                    master_delivery_address["Confiance"] = 0
                    master_delivery_address["Statut"] = "Aucun SHIPTO ne correspond aux preuves du document"
                    master_delivery_address["reason_codes"] = scoring_result.reason_codes
                    master_delivery_address["scoring_decision"] = scoring_result.decision or "REJECTED"
        except Exception:
            pass  # Scoring is non-blocking; keep existing master_delivery_address

    soldto_id = context.get("known_soldto_id") or master_delivery_address.get("SOLDTO")
    order_validation = validate_order_number(get_master_data(), final_order_number, soldto_id)
    cross_validation = build_cross_validation(order_validation, master_delivery_address)

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

        # --- EDIFACT D96A: generate message if not blocked ---
    edifact_message = None
    edifact_errors = None
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
            order_obj = structured_to_order(edifact_input)
            interchange_ref = f"LA{final_order_number or 'X'}".replace("/", "")[:14]
            edifact_message = build_orders_d96a(order=order_obj, interchange_ref=interchange_ref)
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
