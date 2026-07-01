"""Canonical rejection catalog for the EDIFACT Orders Generator.

Every rejection raised anywhere in the pipeline maps to one of these codes.
Each entry is bilingual (FR / EN) and carries routing metadata used by
email_service.py, datatables.py, and the Gradio UI status panel.
"""
from __future__ import annotations

from typing import TypedDict


class RejectionEntry(TypedDict):
    severity: str                 # BLOCKER | BUSINESS_REJECT | TECHNICAL
    business_status: str          # REJECTED | DUPLICATE | DELIVERY_FAILED | PENDING_USER_INPUT
    retry_allowed: bool
    manual_review_required: bool
    message_fr: str
    message_en: str


REJECTION_CATALOG: dict[str, RejectionEntry] = {
    "PDF_PARSE_FAILURE": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Le PDF n'a pas pu être lu ou analysé correctement.",
        "message_en": "The PDF could not be read or parsed correctly.",
    },
    "NOT_A_PDF": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Le fichier soumis n'est pas un PDF valide.",
        "message_en": "The submitted file is not a valid PDF.",
    },
    "ORDER_KEY_MISSING": {
        "severity": "BUSINESS_REJECT",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Le numéro de commande client est manquant.",
        "message_en": "The customer purchase order number is missing.",
    },
    "NO_VALID_ARTICLE": {
        "severity": "BUSINESS_REJECT",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Un ou plusieurs codes articles sont invalides ou absents du référentiel.",
        "message_en": "One or more article codes are invalid or missing from master data.",
    },
    "CONTRACT_KEYWORD": {
        "severity": "BUSINESS_REJECT",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Le document contient un mot-clé contrat/devis — ce n'est pas un bon de commande.",
        "message_en": "The document contains a contract/quotation keyword — this is not a purchase order.",
    },
    "CONTRACT_BREAK_ADDRESSES_MISSING": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Aucune adresse exploitable n'a été trouvée pour résoudre le SHIP-TO.",
        "message_en": "No usable address was found to resolve the SHIP-TO.",
    },
    "CONTRACT_BREAK_ARTICLES_MISSING": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Aucune ligne article exploitable n'a été trouvée.",
        "message_en": "No usable order line item was found.",
    },
    "CONTRACT_BREAK_SOLDTO_MISSING": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Le SOLD-TO n'a pas pu être déterminé.",
        "message_en": "The SOLD-TO could not be resolved.",
    },
    "CONTRACT_BREAK_SHIPTO_CANDIDATES_MISSING": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Aucun candidat SHIP-TO n'a été trouvé dans la famille SOLD-TO.",
        "message_en": "No SHIP-TO candidate was found in the SOLD-TO family.",
    },
    "SOLDTO_NOT_FOUND": {
        "severity": "BUSINESS_REJECT",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Aucun SOLD-TO correspondant n'a été trouvé dans les données maîtres.",
        "message_en": "No matching SOLD-TO was found in master data.",
    },
    "SOLDTO_AMBIGUOUS_MATCH": {
        "severity": "BUSINESS_REJECT",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Plusieurs SOLD-TO correspondent avec une confiance équivalente.",
        "message_en": "Multiple SOLD-TO candidates matched with equivalent confidence.",
    },
    "SHIPTO_WEAK_EVIDENCE_IN_SOLDTO_FAMILY": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Le SHIP-TO n'a pas de preuve forte code postal ou ville. Une rue seule est insuffisante.",
        "message_en": "The SHIP-TO has no strong postal-code or city evidence. Street-only is not sufficient.",
    },
    "SHIPTO_NO_STRONG_MATCH": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Des candidats SHIP-TO existent mais aucun ne correspond avec une preuve forte.",
        "message_en": "SHIP-TO candidates exist but none matched with strong evidence.",
    },
    "SHIPTO_AMBIGUOUS_MATCH": {
        "severity": "BUSINESS_REJECT",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Plusieurs SHIP-TO correspondent avec une preuve forte équivalente.",
        "message_en": "Multiple SHIP-TO candidates matched with equivalent strong evidence.",
    },
    "EDIFACT_MISSING_BGM": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Le segment EDIFACT BGM ne contient pas la référence de commande obligatoire.",
        "message_en": "The EDIFACT BGM segment is missing the mandatory order reference.",
    },
    "EDIFACT_MISSING_DTM_137": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "La date document DTM+137 est manquante ou invalide.",
        "message_en": "The DTM+137 document date is missing or invalid.",
    },
    "EDIFACT_MISSING_NAD_BY": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Le segment acheteur NAD+BY est incomplet.",
        "message_en": "The buyer NAD+BY segment is incomplete.",
    },
    "EDIFACT_MISSING_NAD_DP": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Le segment livraison NAD+DP est incomplet ou non résolu.",
        "message_en": "The delivery NAD+DP segment is incomplete or unresolved.",
    },
    "EDIFACT_MISSING_LIN": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Les segments lignes EDIFACT LIN/PIA/IMD/QTY/PRI sont manquants ou incomplets.",
        "message_en": "The EDIFACT line segments LIN/PIA/IMD/QTY/PRI are missing or incomplete.",
    },
    "ARTICLE_QUANTITY_INVALID": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Une ou plusieurs quantités article sont invalides.",
        "message_en": "One or more article quantities are invalid.",
    },
    "UNIT_PRICE_MISSING": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Un ou plusieurs prix unitaires sont manquants.",
        "message_en": "One or more unit prices are missing.",
    },
    "EDIFACT_LINE_INTEGRITY_MISMATCH": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "La cohérence des lignes EDIFACT est incorrecte.",
        "message_en": "The EDIFACT line integrity check failed.",
    },
    "EDIFACT_NAD_DP_MISMATCH": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Le SHIP-TO sélectionné ne correspond pas au segment NAD+DP généré.",
        "message_en": "The selected SHIP-TO does not match the generated NAD+DP segment.",
    },
    "DUPLICATE_ALREADY_SENT": {
        "severity": "BUSINESS_REJECT",
        "business_status": "DUPLICATE",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Cette commande a déjà été traitée et envoyée.",
        "message_en": "This order has already been processed and sent.",
    },
    # ------------------------------------------------------------------ #
    # Esker / FILE2EDI Esker rules (ported from rejection_engine.py)     #
    # These codes map to the 9 Esker rejection rules checked in          #
    # src/rejection_engine.py check_rejections().                        #
    # ------------------------------------------------------------------ #
    "DELIVERY_ADDRESS_INVALID": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "L'adresse de livraison n'a pas pu être associée aux données maîtres (confiance trop faible).",
        "message_en": "The delivery address could not be matched to masterdata (confidence too low).",
    },
    "NO_DELIVERY_ADDRESS": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Aucune adresse de livraison n'a été détectée dans le document.",
        "message_en": "No delivery address was detected in the document.",
    },
    "ARTICLE_NOT_FOUND": {
        "severity": "BUSINESS_REJECT",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Un ou plusieurs codes articles sont introuvables dans le référentiel matières.",
        "message_en": "One or more article codes were not found in the materials master.",
    },
    "PO_NUMBER_DUPLICATE": {
        "severity": "BUSINESS_REJECT",
        "business_status": "DUPLICATE",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Ce numéro de commande existe déjà dans l'historique SAP des ventes.",
        "message_en": "This purchase order number already exists in the SAP sales order history.",
    },
    "CUSTOMER_NOT_DEFINED": {
        "severity": "BUSINESS_REJECT",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Aucun client (SOLD-TO) n'a pu être identifié dans les données maîtres.",
        "message_en": "No customer (SOLD-TO) could be identified in masterdata.",
    },
    "NOT_AN_ORDER": {
        "severity": "BUSINESS_REJECT",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Le document soumis n'est pas un bon de commande (contrat, devis, proforma…).",
        "message_en": "The submitted document is not a purchase order (contract, quote, proforma…).",
    },
    "NO_LINE_ITEMS": {
        "severity": "BUSINESS_REJECT",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Aucune ligne article n'a été trouvée dans le document.",
        "message_en": "No order line items were found in the document.",
    },
    "QUANTITY_MISSING": {
        "severity": "BUSINESS_REJECT",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "La quantité est manquante sur une ou plusieurs lignes article.",
        "message_en": "Quantity is missing on one or more order lines.",
    },
    "PRICE_MISSING": {
        "severity": "BUSINESS_REJECT",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Le prix unitaire est manquant sur une ou plusieurs lignes article.",
        "message_en": "Unit price is missing on one or more order lines.",
    },
    "DELIVERY_SFTP_FAILED": {
        "severity": "TECHNICAL",
        "business_status": "DELIVERY_FAILED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Le fichier .tst a été généré mais l'envoi SFTP a échoué.",
        "message_en": "The .tst file was generated but the SFTP delivery failed.",
    },
    "DELIVERY_EMAIL_FAILED": {
        "severity": "TECHNICAL",
        "business_status": "DELIVERY_FAILED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Le fichier .tst a été généré mais l'envoi email a échoué.",
        "message_en": "The .tst file was generated but the email delivery failed.",
    },
}

# Action text shown in rejection emails (French)
REJECTION_ACTION_TEXT: dict[str, str] = {
    "PDF_PARSE_FAILURE": "Merci de vérifier la lisibilité du PDF ou de déposer un PDF non scanné si disponible.",
    "ORDER_KEY_MISSING": "Merci de renseigner le numéro de commande client.",
    "NO_VALID_ARTICLE": "Merci de fournir les codes articles Bosch valides ou de corriger les codes client.",
    "CONTRACT_KEYWORD": "Merci de soumettre uniquement des bons de commande, pas des contrats ou devis.",
    "SOLDTO_NOT_FOUND": "Merci de vérifier la TVA / le client SOLD-TO dans les données maîtres.",
    "SHIPTO_WEAK_EVIDENCE_IN_SOLDTO_FAMILY": "Merci de vérifier l'adresse de livraison et les données partenaires WE/SH.",
    "SHIPTO_NO_STRONG_MATCH": "Merci de vérifier le code postal ou la ville du lieu de livraison.",
    "SHIPTO_AMBIGUOUS_MATCH": "Merci de choisir le bon SHIP-TO parmi les candidats proposés.",
    "EDIFACT_MISSING_NAD_DP": "Merci de corriger la résolution SHIP-TO avant génération EDIFACT.",
    "EDIFACT_MISSING_LIN": "Merci de vérifier les lignes articles détectées.",
    "DUPLICATE_ALREADY_SENT": "Merci de confirmer si la commande doit être retraitée ou ignorée.",
    "DELIVERY_ADDRESS_INVALID": "Merci de vérifier l'adresse de livraison ou de la corriger dans le document.",
    "NO_DELIVERY_ADDRESS": "Merci de vous assurer que l'adresse de livraison est clairement indiquée dans le bon de commande.",
    "ARTICLE_NOT_FOUND": "Merci de vérifier les codes articles Bosch ou de les corriger dans le bon de commande.",
    "PO_NUMBER_DUPLICATE": "Ce numéro de commande a déjà été traité. Merci de confirmer si un retraitement est nécessaire.",
    "CUSTOMER_NOT_DEFINED": "Merci de vérifier le client (TVA, nom, code postal) dans les données maîtres.",
    "NOT_AN_ORDER": "Merci de soumettre uniquement des bons de commande (pas des devis, contrats ou proformas).",
    "NO_LINE_ITEMS": "Merci de vérifier que le bon de commande contient au moins une ligne article.",
    "QUANTITY_MISSING": "Merci de vérifier les quantités sur chaque ligne article du bon de commande.",
    "PRICE_MISSING": "Merci de vérifier les prix unitaires sur chaque ligne article du bon de commande.",
    "DELIVERY_SFTP_FAILED": "Merci de vérifier la configuration SFTP ou de relancer uniquement l'envoi.",
}

# Required rejection codes (used by tests)
REQUIRED_CODES = frozenset(REJECTION_CATALOG.keys())


def get(code: str) -> RejectionEntry:
    """Return the catalog entry for *code*, or a fallback entry if unknown."""
    return REJECTION_CATALOG.get(code, {
        "severity": "UNKNOWN",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": f"Erreur inconnue: {code}",
        "message_en": f"Unknown error: {code}",
    })


def action_text(code: str, lang: str = "fr") -> str:
    """Return the recommended action text for a rejection code."""
    default = "Merci de contacter l'équipe BI pour assistance." if lang == "fr" \
              else "Please contact the BI team for assistance."
    return REJECTION_ACTION_TEXT.get(code, default)
