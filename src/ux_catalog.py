"""Business UX rules extracted from the ADV validation reference.

This module is the runtime source of truth for the UX workbook. The workbook
can be removed after review without losing the business rules.
"""
from __future__ import annotations

from typing import TypedDict


class UXChoice(TypedDict):
    label: str
    outcome: str


class UXRule(TypedDict):
    ux_id: str
    group: str
    codes: tuple[str, ...]
    message: str | None
    choices: tuple[UXChoice, ...]
    resolution_mode: str
    requires_recontrol: bool
    finalization_required: bool
    status: str


def _choice(label: str, outcome: str) -> UXChoice:
    return {"label": label, "outcome": outcome}


UX_RULES: tuple[UXRule, ...] = (
    {
        "ux_id": "UX-01", "group": "Document",
        "codes": ("PDF_PARSE_FAILURE", "NOT_A_PDF", "NOT_AN_ORDER", "CONTRACT_KEYWORD", "ORDER_CHANGE"),
        "message": "Génie n'a pas pu confirmer qu'il s'agit d'un bon de commande standard",
        "choices": (
            _choice("J'ai pu saisir la commande", "correct_and_recontrol"),
            _choice("J'ai vérifié : ce document n'est pas un bon de commande", "close_without_sap"),
        ),
        "resolution_mode": "ADV", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-02", "group": "Extraction", "codes": ("EXTRACTION_LLM_SALVAGE",),
        "message": None, "choices": (), "resolution_mode": "SYSTEM",
        "requires_recontrol": False, "finalization_required": False, "status": "active",
    },
    {
        "ux_id": "UX-03", "group": "Commande", "codes": ("ORDER_KEY_MISSING",),
        "message": "Génie n'a pas pu identifier le numéro de commande d'achat",
        "choices": (
            _choice("J'ai renseigné le numéro de commande", "correct_and_recontrol"),
            _choice("J'ai vérifié : l'information n'est pas présente sur le document", "keep_blocked"),
        ),
        "resolution_mode": "ADV + RECONTROL", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-04", "group": "Commande", "codes": ("ORDER_DATE_INVALID",),
        "message": "Génie n'a pas pu identifier la date d'émission de la commande",
        "choices": (
            _choice("J'ai renseigné la date de commande", "correct_and_recontrol"),
            _choice("J'ai vérifié : l'information n'est pas présente sur le document", "keep_blocked"),
        ),
        "resolution_mode": "ADV + RECONTROL", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-05", "group": "Commande", "codes": ("DELIVERY_DATE_INVALID",),
        "message": "Génie n'a pas pu identifier la date de livraison de la commande",
        "choices": (
            _choice("J'ai renseigné la date de livraison de la commande", "correct_and_recontrol"),
            _choice("J'ai vérifié : l'information n'est pas présente sur le document", "keep_blocked"),
        ),
        "resolution_mode": "ADV + RECONTROL", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-06", "group": "Partenaire",
        "codes": ("NO_DELIVERY_ADDRESS", "SHIPTO_CANDIDATES_MISSING", "SHIPTO_NO_STRONG_MATCH", "SHIPTO_AMBIGUOUS_MATCH", "PARTNER_UNRESOLVED"),
        "message": "Génie n'a pas pu identifier le client livré",
        "choices": (
            _choice("J'ai corrigé le client livré", "correct_and_recontrol"),
            _choice("J'ai vérifié : le client livré sélectionné est correct", "confirm_and_recontrol"),
            _choice("Le client livré n'est pas dans la liste des clients livrés", "keep_blocked_and_escalate"),
        ),
        "resolution_mode": "ADV + RECONTROL", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-07", "group": "Partenaire",
        "codes": ("SOLDTO_NOT_FOUND", "SOLDTO_AMBIGUOUS_MATCH", "SHIPTO_SOLDTO_MISMATCH", "PARTNER_UNRESOLVED"),
        "message": "Génie n'a pas pu identifier le sold-to",
        "choices": (
            _choice("J'ai corrigé le Sold-to", "correct_and_recontrol"),
            _choice("J'ai vérifié : le Sold-to sélectionné est correct", "confirm_and_recontrol"),
            _choice("Le Sold-to n'est pas dans la liste des Sold-to", "keep_blocked_and_escalate"),
        ),
        "resolution_mode": "ADV + RECONTROL", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-08", "group": "Article",
        "codes": ("MATERIAL_STATUS_INVALID", "ARTICLE_NOT_FOUND", "NO_VALID_ARTICLE"),
        "message": "Génie n'a pas pu valider la référence article sur la ligne concernée",
        "choices": (
            _choice("J'ai remplacé ou corrigé la référence article", "correct_and_recontrol"),
            _choice("J'ai renseigné une référence de remplacement", "correct_and_recontrol"),
            _choice("J'ai supprimé la ligne concernée", "delete_line_and_recontrol"),
        ),
        "resolution_mode": "ADV + RECONTROL", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-09", "group": "Article", "codes": ("QUANTITY_MISSING", "ARTICLE_QUANTITY_INVALID"),
        "message": "Génie n'a pas pu identifier une quantité valide sur la ligne de commande",
        "choices": (
            _choice("J'ai corrigé la quantité", "correct_and_recontrol"),
            _choice("J'ai vérifié : la quantité n'est pas présente sur le document", "keep_blocked"),
        ),
        "resolution_mode": "ADV + RECONTROL", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-10", "group": "Article", "codes": ("UNIT_PRICE_MISSING",),
        "message": "Génie n'a pas pu identifier le prix unitaire sur la ligne de commande",
        "choices": (
            _choice("J'ai renseigné le prix unitaire", "correct_and_recontrol"),
            _choice("J'ai vérifié : cette commande est acceptée sans prix", "confirm_no_price_and_recontrol"),
        ),
        "resolution_mode": "ADV + RECONTROL", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-11", "group": "Article", "codes": ("NO_LINE_ITEMS",),
        "message": "Génie n'a pas pu identifier de ligne de commande exploitable dans le document",
        "choices": (
            _choice("J'ai ajouté les lignes de commande", "correct_and_recontrol"),
            _choice("J'ai vérifié : le document ne contient aucune ligne exploitable", "keep_blocked_and_escalate"),
        ),
        "resolution_mode": "ADV + RECONTROL", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-12", "group": "Doublon", "codes": ("RESUBMISSION_DETECTED",),
        "message": "Ce document a déjà été déposé et retraité par Génie",
        "choices": (), "resolution_mode": "SYSTEM", "requires_recontrol": False, "finalization_required": False, "status": "active",
    },
    {
        "ux_id": "UX-13", "group": "Doublon", "codes": ("PO_NUMBER_DUPLICATE",),
        "message": "Génie a identifié un numéro de commande déjà présent dans l'historique SAP",
        "choices": (
            _choice("J'ai vérifié : c'est une nouvelle commande", "confirm_new_order_and_recontrol"),
            _choice("J'ai vérifié : cette commande existe déjà dans SAP", "keep_blocked"),
        ),
        "resolution_mode": "ADV + RECONTROL", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-14", "group": "Doublon", "codes": ("DUPLICATE_ALREADY_SENT",),
        "message": "Génie a identifié que cette commande semble avoir déjà été traitée et envoyée",
        "choices": (
            _choice("J'ai vérifié : ce n'est pas la même commande", "confirm_distinct_order_and_recontrol"),
            _choice("J'ai vérifié : cette commande a déjà été envoyée", "keep_blocked"),
        ),
        "resolution_mode": "ADV + RECONTROL", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-15", "group": "Technique", "codes": ("MASTERDATA_MISSING", "MASTERDATA_SCHEMA_INVALID"),
        "message": "Génie ne peut pas vérifier la commande car le référentiel SAP est indisponible ou inexploitable",
        "choices": (
            _choice("Relancer le contrôle du référentiel", "retry_masterdata_check"),
            _choice("J'ai signalé le problème au support", "keep_blocked"),
        ),
        "resolution_mode": "SYSTEM", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-16", "group": "EDI",
        "codes": ("EDIFACT_MISSING_BGM", "EDIFACT_MISSING_DTM_137", "EDIFACT_MISSING_NAD_BY", "EDIFACT_MISSING_NAD_DP", "EDIFACT_MISSING_LIN"),
        "message": "Génie n'a pas pu générer le fichier EDI avec les informations actuelles de la commande",
        "choices": (
            _choice("J'ai corrigé les informations de la commande", "correct_and_regenerate"),
            _choice("J'ai vérifié : les informations sont correctes", "regenerate_and_recontrol"),
            _choice("Je n'ai pas pu corriger les informations", "keep_blocked"),
        ),
        "resolution_mode": "ADV + SYSTEM", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-17", "group": "EDI", "codes": ("EDIFACT_LINE_INTEGRITY_MISMATCH", "EDIFACT_NAD_DP_MISMATCH"),
        "message": "Génie a détecté une incohérence entre la commande et le fichier EDI généré",
        "choices": (
            _choice("J'ai corrigé les informations de la commande", "correct_and_regenerate"),
            _choice("J'ai vérifié : les informations sont correctes", "regenerate_and_recontrol"),
            _choice("Je n'ai pas pu corriger les informations", "keep_blocked"),
        ),
        "resolution_mode": "ADV + SYSTEM", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-18", "group": "Livraison", "codes": ("DELIVERY_SFTP_FAILED", "DELIVERY_EMAIL_FAILED"),
        "message": "Génie n'a pas pu transmettre le fichier EDI vers le destinataire",
        "choices": (
            _choice("J'ai relancé l'envoi", "retry_delivery"),
            _choice("J'ai traité l'envoi manuellement", "confirm_manual_delivery"),
            _choice("Je n'ai pas pu transmettre la commande", "keep_blocked"),
        ),
        "resolution_mode": "ADV + SYSTEM", "requires_recontrol": True, "finalization_required": True, "status": "active",
    },
    {
        "ux_id": "UX-19", "group": "Article / Offre", "codes": (),
        "message": "Évolution à compléter : détection des offres, prix SAP et risque Y11",
        "choices": (), "resolution_mode": "À définir", "requires_recontrol": True, "finalization_required": True, "status": "draft",
    },
    {
        "ux_id": "UX-20", "group": "Livraison / Frais", "codes": (),
        "message": "Évolution à compléter : seuils de frais de port selon client et type d'article",
        "choices": (), "resolution_mode": "À définir", "requires_recontrol": True, "finalization_required": True, "status": "draft",
    },
)


UX_BY_ID = {rule["ux_id"]: rule for rule in UX_RULES}
UX_BY_CODE = {
    code: rule
    for rule in UX_RULES
    if rule["status"] == "active"
    for code in rule["codes"]
}


def ux_rule(code: str) -> UXRule | None:
    """Return the active UX rule for a canonical rejection code."""
    return UX_BY_CODE.get(code)