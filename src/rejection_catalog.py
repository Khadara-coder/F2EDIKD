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


# Legacy / alternate codes → canonical catalog key
CODE_ALIASES: dict[str, str] = {
    "PO_NUMBER_MISSING": "ORDER_KEY_MISSING",
    "ORDER_NUMBER_MISSING": "ORDER_KEY_MISSING",
    "NO_ORDER_LINES": "NO_LINE_ITEMS",
    "ORDER_DATE_MISSING": "ORDER_DATE_INVALID",
    "INVALID_QUANTITY": "ARTICLE_QUANTITY_INVALID",
    "SHIPTO_MISSING": "SHIPTO_NO_STRONG_MATCH",
}


def normalize_code(code: str) -> str:
    """Resolve legacy aliases to the canonical catalog code."""
    raw = (code or "").strip()
    return CODE_ALIASES.get(raw, raw)


REJECTION_CATALOG: dict[str, RejectionEntry] = {
    "PDF_PARSE_FAILURE": {
        "severity": "BLOCKER",
        "business_status": "REJECTED",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Le PDF n'a pas pu être lu ou analysé correctement.",
        "message_en": "The PDF could not be read or parsed correctly.",
    },
    "EXTRACTION_LLM_SALVAGE": {
        "severity": "BUSINESS_REJECT",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Extraction déterministe en échec — données récupérées par fallback IA (revue obligatoire).",
        "message_en": "Deterministic extraction failed — data recovered via AI fallback (manual review required).",
    },
    "PARTNER_UNRESOLVED": {
        "severity": "BUSINESS_REJECT",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Sold-to / Ship-to non validés automatiquement — saisie manuelle requise.",
        "message_en": "Sold-to / Ship-to could not be auto-validated — manual entry required.",
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
    "ORDER_DATE_INVALID": {
        "severity": "BUSINESS_REJECT",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "La date de commande est manquante ou invalide.",
        "message_en": "The order date is missing or invalid.",
    },
    "DELIVERY_DATE_INVALID": {
        "severity": "BUSINESS_REJECT",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Une date de livraison de ligne est manquante ou invalide.",
        "message_en": "A line delivery date is missing or invalid.",
    },
    "ORDER_CHANGE": {
        "severity": "BUSINESS_REJECT",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": "Le document est une modification de commande, pas un bon de commande initial.",
        "message_en": "The document is an order change, not an initial purchase order.",
    },
    "MASTERDATA_MISSING": {
        "severity": "TECHNICAL",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Les données maîtres sont absentes ou vides - synchronisation requise.",
        "message_en": "Master data is missing or empty - synchronization required.",
    },
    "MASTERDATA_SCHEMA_INVALID": {
        "severity": "TECHNICAL",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Le schéma des données maîtres est invalide (colonnes manquantes).",
        "message_en": "Master data schema is invalid (missing columns).",
    },
    "MATERIAL_STATUS_INVALID": {
        "severity": "BUSINESS_REJECT",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": (
            "Le statut matière bloque la vente (arrêté, remplacement ou introuvable). "
            "Le message de la ligne précise la référence, la date et le code de remplacement."
        ),
        "message_en": (
            "Material status blocks sales (discontinued, replacement, or not found). "
            "The line message states the reference, date, and replacement code."
        ),
    },
    "RESUBMISSION_DETECTED": {
        "severity": "TECHNICAL",
        "business_status": "PENDING_USER_INPUT",
        "retry_allowed": True,
        "manual_review_required": True,
        "message_fr": "Ce PDF a déjà été soumis - la commande est recalculée.",
        "message_en": "This PDF was already submitted - the order is recalculated.",
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
        "message_fr": "Le document contient un mot-clé contrat/devis - ce n'est pas un bon de commande.",
        "message_en": "The document contains a contract/quotation keyword - this is not a purchase order.",
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
        "message_fr": "L'adresse de livraison n'a pas pu être associée aux données maîtres en raison d'une mauvaise détection ou de données client manquantes.",
        "message_en": "The delivery address could not be matched to master data due to poor detection or missing customer data.",
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
        "message_fr": "Ce numéro de commande existe déjà dans l'historique SAP.",
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
    "EXTRACTION_LLM_SALVAGE": "Vérifiez les données extraites par l'IA (lignes, client, adresse) avant validation.",
    "PARTNER_UNRESOLVED": "Merci de sélectionner manuellement le sold-to et le ship-to dans la revue.",
    "NOT_A_PDF": "Merci de déposer un fichier PDF valide.",
    "ORDER_KEY_MISSING": "Merci de renseigner le numéro de commande client.",
    "ORDER_DATE_INVALID": "Merci de corriger la date de commande (format JJ/MM/AAAA).",
    "DELIVERY_DATE_INVALID": "Merci de corriger la date de livraison sur la ligne concernée.",
    "ORDER_CHANGE": "Merci de soumettre un bon de commande initial, pas une modification.",
    "MASTERDATA_MISSING": "Merci de synchroniser les données maîtres (Clients / Articles) puis de relancer.",
    "MASTERDATA_SCHEMA_INVALID": "Merci de vérifier le fichier masterdata et de resynchroniser.",
    "MATERIAL_STATUS_INVALID": (
        "Ouvrez la ligne concernée : si la référence est remplacée, utilisez le nouveau code Bosch ; "
        "si elle est arrêtée, retirez ou substituez la ligne ; si elle est introuvable, corrigez le code "
        "ou synchronisez les données maîtres Articles."
    ),
    "RESUBMISSION_DETECTED": "Vérifier si le retraitement est intentionnel avant validation.",
    "NO_VALID_ARTICLE": "Merci de fournir les codes articles Bosch valides ou de corriger les codes client.",
    "CONTRACT_KEYWORD": "Merci de soumettre uniquement des bons de commande, pas des contrats ou devis.",
    "CONTRACT_BREAK_ADDRESSES_MISSING": "Merci de vérifier l'adresse de livraison dans le document.",
    "CONTRACT_BREAK_ARTICLES_MISSING": "Merci de vérifier que le bon de commande contient des lignes articles.",
    "CONTRACT_BREAK_SOLDTO_MISSING": "Merci de vérifier le client (TVA, nom) dans les données maîtres.",
    "CONTRACT_BREAK_SHIPTO_CANDIDATES_MISSING": "Merci de vérifier l'adresse de livraison et les partenaires WE/SH.",
    "SOLDTO_NOT_FOUND": "Merci de vérifier la TVA / le client SOLD-TO dans les données maîtres.",
    "SOLDTO_AMBIGUOUS_MATCH": "Merci de choisir le bon SOLD-TO parmi les candidats proposés.",
    "SHIPTO_WEAK_EVIDENCE_IN_SOLDTO_FAMILY": "Merci de vérifier l'adresse de livraison et les données partenaires WE/SH.",
    "SHIPTO_NO_STRONG_MATCH": "Merci de vérifier le code postal ou la ville du lieu de livraison.",
    "SHIPTO_AMBIGUOUS_MATCH": "Merci de choisir le bon SHIP-TO parmi les candidats proposés.",
    "EDIFACT_MISSING_BGM": "Merci de renseigner la référence de commande avant génération EDIFACT.",
    "EDIFACT_MISSING_DTM_137": "Merci de corriger la date document avant génération EDIFACT.",
    "EDIFACT_MISSING_NAD_BY": "Merci de corriger le SOLD-TO / acheteur avant génération EDIFACT.",
    "EDIFACT_MISSING_NAD_DP": "Merci de corriger la résolution SHIP-TO avant génération EDIFACT.",
    "EDIFACT_MISSING_LIN": "Merci de vérifier les lignes articles détectées.",
    "ARTICLE_QUANTITY_INVALID": "Merci de corriger la quantité sur la ligne concernée.",
    "UNIT_PRICE_MISSING": "Merci de renseigner le prix unitaire sur la ligne concernée.",
    "EDIFACT_LINE_INTEGRITY_MISMATCH": "Merci de réconcilier les lignes avant génération EDIFACT.",
    "EDIFACT_NAD_DP_MISMATCH": "Merci d'aligner le SHIP-TO sélectionné avec NAD+DP.",
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
    "DELIVERY_EMAIL_FAILED": "Merci de vérifier la configuration email ou de relancer uniquement l'envoi.",
}

# Required rejection codes (used by tests)
REQUIRED_CODES = frozenset(REJECTION_CATALOG.keys())


class ReviewActions(TypedDict):
    button_accept: str
    button_reject: str
    auto_action_accept: str
    auto_action_reject: str
    mode: str  # Manuel | Automatique | Semi-auto


DEFAULT_REVIEW_ACTIONS: ReviewActions = {
    "button_accept": "Valider",
    "button_reject": "Ignorer",
    "auto_action_accept": "Continuer le traitement",
    "auto_action_reject": "Clôturer l'anomalie sans correction",
    "mode": "Manuel",
}

# UI labels + future automatic actions for each rejection code (manual review buttons).
REJECTION_REVIEW_ACTIONS: dict[str, ReviewActions] = {
    "ORDER_DATE_INVALID": {
        "button_accept": "Date commande corrigée",
        "button_reject": "Date commande invalide",
        "auto_action_accept": "Continuer avec la date saisie",
        "auto_action_reject": "Mettre en attente de saisie",
        "mode": "Manuel",
    },
    "DELIVERY_DATE_INVALID": {
        "button_accept": "Date livraison corrigée",
        "button_reject": "Date livraison invalide",
        "auto_action_accept": "Continuer avec la date saisie",
        "auto_action_reject": "Mettre la ligne en attente",
        "mode": "Manuel",
    },
    "ORDER_CHANGE": {
        "button_accept": "Traiter comme commande initiale",
        "button_reject": "Ce n'est pas une commande initiale",
        "auto_action_accept": "Continuer le traitement",
        "auto_action_reject": "Clôturer comme modification de commande",
        "mode": "Manuel",
    },
    "MASTERDATA_MISSING": {
        "button_accept": "Masterdata synchronisée, relancer",
        "button_reject": "Impossible de synchroniser",
        "auto_action_accept": "Relancer après sync masterdata",
        "auto_action_reject": "Bloquer la génération",
        "mode": "Semi-auto",
    },
    "MASTERDATA_SCHEMA_INVALID": {
        "button_accept": "Schéma corrigé, relancer",
        "button_reject": "Schéma toujours invalide",
        "auto_action_accept": "Relancer après correction schéma",
        "auto_action_reject": "Bloquer la génération",
        "mode": "Semi-auto",
    },
    "MATERIAL_STATUS_INVALID": {
        "button_accept": "Référence corrigée (nouveau code / ligne OK)",
        "button_reject": "Impossible de corriger la référence",
        "auto_action_accept": "Continuer avec la référence validée",
        "auto_action_reject": "Bloquer ou retirer la ligne",
        "mode": "Manuel",
    },
    "RESUBMISSION_DETECTED": {
        "button_accept": "Retraitement intentionnel",
        "button_reject": "Ignorer l'alerte",
        "auto_action_accept": "Continuer le recalcul",
        "auto_action_reject": "Clôturer l'alerte de resoumission",
        "mode": "Manuel",
    },
    "PDF_PARSE_FAILURE": {
        "button_accept": "PDF relu, relancer l'extraction",
        "button_reject": "Rejeter le fichier",
        "auto_action_accept": "Relancer l'extraction OCR",
        "auto_action_reject": "Clôturer la commande comme rejetée",
        "mode": "Manuel",
    },
    "EXTRACTION_LLM_SALVAGE": {
        "button_accept": "Données IA validées",
        "button_reject": "Données IA incorrectes",
        "auto_action_accept": "Continuer la revue avec les données pré-remplies",
        "auto_action_reject": "Rejeter et re-saisir manuellement",
        "mode": "Manuel",
    },
    "PARTNER_UNRESOLVED": {
        "button_accept": "Partners sélectionnés",
        "button_reject": "Partners introuvables",
        "auto_action_accept": "Continuer avec les partners choisis",
        "auto_action_reject": "Clôturer faute de partners",
        "mode": "Manuel",
    },
    "NOT_A_PDF": {
        "button_accept": "Fichier corrigé, reprendre",
        "button_reject": "Ce n'est pas un PDF valide",
        "auto_action_accept": "Relancer le traitement",
        "auto_action_reject": "Clôturer comme fichier invalide",
        "mode": "Manuel",
    },
    "ORDER_KEY_MISSING": {
        "button_accept": "N° commande renseigné",
        "button_reject": "Impossible de retrouver le n°",
        "auto_action_accept": "Continuer avec le n° saisi",
        "auto_action_reject": "Mettre en attente de saisie",
        "mode": "Manuel",
    },
    "NO_VALID_ARTICLE": {
        "button_accept": "Articles corrigés",
        "button_reject": "Rejeter les lignes invalides",
        "auto_action_accept": "Continuer avec les articles validés",
        "auto_action_reject": "Retirer les lignes invalides",
        "mode": "Manuel",
    },
    "CONTRACT_KEYWORD": {
        "button_accept": "C'est bien une commande",
        "button_reject": "Ce n'est pas une commande",
        "auto_action_accept": "Continuer le traitement",
        "auto_action_reject": "Clôturer comme document non commande",
        "mode": "Manuel",
    },
    "CONTRACT_BREAK_ADDRESSES_MISSING": {
        "button_accept": "Adresse corrigée",
        "button_reject": "Adresse introuvable",
        "auto_action_accept": "Relancer la résolution SHIP-TO",
        "auto_action_reject": "Clôturer faute d'adresse",
        "mode": "Manuel",
    },
    "CONTRACT_BREAK_ARTICLES_MISSING": {
        "button_accept": "Lignes articles corrigées",
        "button_reject": "Aucune ligne exploitable",
        "auto_action_accept": "Continuer avec les lignes saisies",
        "auto_action_reject": "Clôturer faute de lignes",
        "mode": "Manuel",
    },
    "CONTRACT_BREAK_SOLDTO_MISSING": {
        "button_accept": "SOLD-TO sélectionné",
        "button_reject": "SOLD-TO introuvable",
        "auto_action_accept": "Continuer avec le SOLD-TO choisi",
        "auto_action_reject": "Clôturer faute de SOLD-TO",
        "mode": "Manuel",
    },
    "CONTRACT_BREAK_SHIPTO_CANDIDATES_MISSING": {
        "button_accept": "SHIP-TO sélectionné",
        "button_reject": "Aucun SHIP-TO candidat",
        "auto_action_accept": "Continuer avec le SHIP-TO choisi",
        "auto_action_reject": "Clôturer faute de SHIP-TO",
        "mode": "Manuel",
    },
    "SOLDTO_NOT_FOUND": {
        "button_accept": "Client identifié manuellement",
        "button_reject": "Client inconnu",
        "auto_action_accept": "Appliquer le SOLD-TO saisi",
        "auto_action_reject": "Clôturer comme client inconnu",
        "mode": "Manuel",
    },
    "SOLDTO_AMBIGUOUS_MATCH": {
        "button_accept": "J'ai choisi le bon SOLD-TO",
        "button_reject": "Ambiguïté non résolue",
        "auto_action_accept": "Appliquer le SOLD-TO choisi",
        "auto_action_reject": "Mettre en attente de clarification",
        "mode": "Manuel",
    },
    "SHIPTO_WEAK_EVIDENCE_IN_SOLDTO_FAMILY": {
        "button_accept": "Adresse de livraison confirmée",
        "button_reject": "Adresse insuffisante",
        "auto_action_accept": "Continuer avec le SHIP-TO confirmé",
        "auto_action_reject": "Clôturer faute de preuve adresse",
        "mode": "Manuel",
    },
    "SHIPTO_NO_STRONG_MATCH": {
        "button_accept": "SHIP-TO confirmé",
        "button_reject": "Pas de correspondance fiable",
        "auto_action_accept": "Appliquer le SHIP-TO confirmé",
        "auto_action_reject": "Clôturer faute de match SHIP-TO",
        "mode": "Manuel",
    },
    "SHIPTO_AMBIGUOUS_MATCH": {
        "button_accept": "J'ai choisi le bon SHIP-TO",
        "button_reject": "Ambiguïté non résolue",
        "auto_action_accept": "Appliquer le SHIP-TO choisi",
        "auto_action_reject": "Mettre en attente de clarification",
        "mode": "Manuel",
    },
    "EDIFACT_MISSING_BGM": {
        "button_accept": "Référence commande corrigée",
        "button_reject": "Impossible de générer le BGM",
        "auto_action_accept": "Régénérer l'EDIFACT",
        "auto_action_reject": "Bloquer la génération EDIFACT",
        "mode": "Manuel",
    },
    "EDIFACT_MISSING_DTM_137": {
        "button_accept": "Date document corrigée",
        "button_reject": "Date document invalide",
        "auto_action_accept": "Régénérer l'EDIFACT",
        "auto_action_reject": "Bloquer la génération EDIFACT",
        "mode": "Manuel",
    },
    "EDIFACT_MISSING_NAD_BY": {
        "button_accept": "Acheteur corrigé",
        "button_reject": "Acheteur incomplet",
        "auto_action_accept": "Régénérer l'EDIFACT",
        "auto_action_reject": "Bloquer la génération EDIFACT",
        "mode": "Manuel",
    },
    "EDIFACT_MISSING_NAD_DP": {
        "button_accept": "Livraison corrigée",
        "button_reject": "Livraison non résolue",
        "auto_action_accept": "Régénérer l'EDIFACT",
        "auto_action_reject": "Bloquer la génération EDIFACT",
        "mode": "Manuel",
    },
    "EDIFACT_MISSING_LIN": {
        "button_accept": "Lignes articles corrigées",
        "button_reject": "Aucune ligne LIN",
        "auto_action_accept": "Régénérer l'EDIFACT",
        "auto_action_reject": "Bloquer la génération EDIFACT",
        "mode": "Manuel",
    },
    "ARTICLE_QUANTITY_INVALID": {
        "button_accept": "Quantité corrigée",
        "button_reject": "Quantité invalide",
        "auto_action_accept": "Continuer avec la quantité saisie",
        "auto_action_reject": "Retirer ou bloquer la ligne",
        "mode": "Manuel",
    },
    "UNIT_PRICE_MISSING": {
        "button_accept": "Prix unitaire renseigné",
        "button_reject": "Prix manquant",
        "auto_action_accept": "Continuer avec le prix saisi",
        "auto_action_reject": "Mettre la ligne en attente",
        "mode": "Manuel",
    },
    "EDIFACT_LINE_INTEGRITY_MISMATCH": {
        "button_accept": "Lignes réconciliées",
        "button_reject": "Écart de lignes",
        "auto_action_accept": "Régénérer l'EDIFACT",
        "auto_action_reject": "Bloquer la génération EDIFACT",
        "mode": "Manuel",
    },
    "EDIFACT_NAD_DP_MISMATCH": {
        "button_accept": "SHIP-TO aligné",
        "button_reject": "Écart NAD+DP",
        "auto_action_accept": "Régénérer l'EDIFACT",
        "auto_action_reject": "Bloquer la génération EDIFACT",
        "mode": "Manuel",
    },
    "DUPLICATE_ALREADY_SENT": {
        "button_accept": "J'ai vérifié, c'est une nouvelle commande",
        "button_reject": "Cette commande existe déjà",
        "auto_action_accept": "Continuer le traitement / renvoyer vers SAP",
        "auto_action_reject": "Clôturer comme doublon déjà envoyé",
        "mode": "Manuel",
    },
    "DELIVERY_ADDRESS_INVALID": {
        "button_accept": "Adresse de livraison corrigée",
        "button_reject": "Adresse non associative",
        "auto_action_accept": "Relancer le matching adresse",
        "auto_action_reject": "Clôturer faute d'adresse",
        "mode": "Manuel",
    },
    "NO_DELIVERY_ADDRESS": {
        "button_accept": "Adresse de livraison saisie",
        "button_reject": "Aucune adresse de livraison",
        "auto_action_accept": "Continuer avec l'adresse saisie",
        "auto_action_reject": "Clôturer faute d'adresse",
        "mode": "Manuel",
    },
    "ARTICLE_NOT_FOUND": {
        "button_accept": "Accepter le matériau",
        "button_reject": "Rejeter la ligne",
        "auto_action_accept": "Continuer avec le matériau validé",
        "auto_action_reject": "Retirer la ligne article",
        "mode": "Manuel",
    },
    "PO_NUMBER_DUPLICATE": {
        "button_accept": "J'ai vérifié, c'est une nouvelle commande",
        "button_reject": "Cette commande existe déjà",
        "auto_action_accept": "Continuer le traitement",
        "auto_action_reject": "Clôturer comme doublon",
        "mode": "Manuel",
    },
    "CUSTOMER_NOT_DEFINED": {
        "button_accept": "Client identifié",
        "button_reject": "Client non défini",
        "auto_action_accept": "Appliquer le client saisi",
        "auto_action_reject": "Clôturer comme client inconnu",
        "mode": "Manuel",
    },
    "NOT_AN_ORDER": {
        "button_accept": "C'est bien une commande",
        "button_reject": "Ce n'est pas une commande",
        "auto_action_accept": "Continuer le traitement",
        "auto_action_reject": "Clôturer comme document non commande",
        "mode": "Manuel",
    },
    "NO_LINE_ITEMS": {
        "button_accept": "Lignes articles ajoutées",
        "button_reject": "Aucune ligne article",
        "auto_action_accept": "Continuer avec les lignes saisies",
        "auto_action_reject": "Clôturer faute de lignes",
        "mode": "Manuel",
    },
    "QUANTITY_MISSING": {
        "button_accept": "Quantité renseignée",
        "button_reject": "Quantité manquante",
        "auto_action_accept": "Continuer avec la quantité saisie",
        "auto_action_reject": "Mettre la ligne en attente",
        "mode": "Manuel",
    },
    "PRICE_MISSING": {
        "button_accept": "Prix renseigné",
        "button_reject": "Prix manquant",
        "auto_action_accept": "Continuer avec le prix saisi",
        "auto_action_reject": "Mettre la ligne en attente",
        "mode": "Manuel",
    },
    "DELIVERY_SFTP_FAILED": {
        "button_accept": "Relancer l'envoi SFTP",
        "button_reject": "Abandonner l'envoi",
        "auto_action_accept": "Relancer l'upload SFTP",
        "auto_action_reject": "Marquer l'échec SFTP comme clôturé",
        "mode": "Semi-auto",
    },
    "DELIVERY_EMAIL_FAILED": {
        "button_accept": "Relancer l'envoi email",
        "button_reject": "Abandonner l'envoi",
        "auto_action_accept": "Relancer l'envoi email",
        "auto_action_reject": "Marquer l'échec email comme clôturé",
        "mode": "Semi-auto",
    },
}


def get(code: str) -> RejectionEntry:
    """Return the catalog entry for *code*, or a fallback entry if unknown."""
    canonical = normalize_code(code)
    return REJECTION_CATALOG.get(canonical, {
        "severity": "UNKNOWN",
        "business_status": "REJECTED",
        "retry_allowed": False,
        "manual_review_required": True,
        "message_fr": f"Erreur inconnue: {code}",
        "message_en": f"Unknown error: {code}",
    })


def format_rejection_message(
    code: str,
    details: dict | None = None,
    fallback: str = "",
) -> str:
    """Return a French user-facing message for a rejection code."""
    code = normalize_code(code)
    entry = get(code)
    base = (entry.get("message_fr") or fallback or code).strip()
    details = details or {}

    if code == "PO_NUMBER_DUPLICATE":
        po = str(details.get("po_number") or details.get("po") or "").strip()
        if po:
            return f"Ce numéro de commande {po} existe déjà dans l'historique SAP."
        return base

    if code == "QUANTITY_MISSING":
        lines = details.get("lines") or []
        if lines:
            return f"Quantité manquante sur la/les ligne(s) : {', '.join(str(l) for l in lines)}."
        return base

    if code == "PRICE_MISSING":
        lines = details.get("lines") or []
        if lines:
            return f"Prix unitaire manquant sur la/les ligne(s) : {', '.join(str(l) for l in lines)}."
        return base

    if code == "ARTICLE_NOT_FOUND":
        articles = details.get("articles") or []
        if articles:
            if isinstance(articles[0], dict):
                art_list = ", ".join(str(a.get("article") or "") for a in articles[:5])
                count = len(articles)
            else:
                art_list = ", ".join(str(a) for a in articles[:5])
                count = len(articles)
            if art_list:
                return f"{count} article(s) inconnu(s) dans le référentiel : {art_list}."
        return base

    if code == "DELIVERY_ADDRESS_INVALID":
        conf = details.get("confiance")
        if conf is not None and conf != "":
            return f"{base} (confiance {conf} %)."
        return base

    if code == "NOT_AN_ORDER" and details.get("detected_type"):
        return f"Le document semble être un {details['detected_type']}, pas un bon de commande."

    if code == "ORDER_CHANGE" and details.get("detected_type"):
        return f"Document de modification de commande (type : {details['detected_type']})."

    if code == "MATERIAL_STATUS_INVALID":
        fallback_msg = str(fallback or "").strip()
        if fallback_msg:
            return fallback_msg
        matnr = str(details.get("matnr") or details.get("article") or "").strip()
        if matnr:
            try:
                from src.masterdata_runtime import format_material_status_anomaly_message

                line_number = details.get("line_number") or details.get("lineNumber")
                built = format_material_status_anomaly_message(
                    line_number=line_number,
                    matnr=matnr,
                )
                if built:
                    return built["message"]
            except Exception:
                pass
        return base

    return base


def review_actions(code: str) -> ReviewActions:
    """Return button labels and future auto-actions for a rejection code."""
    canonical = normalize_code(code)
    override = REJECTION_REVIEW_ACTIONS.get(canonical)
    if not override:
        return dict(DEFAULT_REVIEW_ACTIONS)
    return {**DEFAULT_REVIEW_ACTIONS, **override}


def action_text(code: str, lang: str = "fr") -> str:
    """Return the recommended action text for a rejection code."""
    canonical = normalize_code(code)
    default = "Merci de contacter l'équipe BI pour assistance." if lang == "fr" \
              else "Please contact the BI team for assistance."
    return REJECTION_ACTION_TEXT.get(canonical, default)
