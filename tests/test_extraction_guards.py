from app.extraction import (
    _choose_final_date,
    _finalize_document_totals,
    _merge_order_line_candidates,
    _sanitize_order_lines,
)


def test_choose_final_date_prefers_strong_anchor_over_implausible_llm():
    result = _choose_final_date(
        "1945-05-08",
        "2024-04-03",
        "line_context",
        ["2024-04-03"],
    )
    assert result == "2024-04-03"


def test_choose_final_date_accepts_llm_date_seen_in_document_when_anchor_is_weak():
    result = _choose_final_date(
        "2024-02-13",
        "2024-02-09",
        "fallback_all_dates",
        ["2024-02-09", "2024-02-13"],
    )
    assert result == "2024-02-13"


def test_finalize_document_totals_falls_back_to_sum_of_lines():
    totals, total_lignes_ht = _finalize_document_totals(
        {"Total HT": None, "Total TTC": None},
        [
            {"montant_ligne_ht": 10.0},
            {"montant_ligne_ht": 2.5},
        ],
    )

    assert total_lignes_ht == 12.5
    assert totals["Total HT"] == "12,50 EUR"
    assert totals["Total TTC"] is None


def test_sanitize_order_lines_drops_polluted_incoherent_lines():
    cleaned = _sanitize_order_lines(
        [
            {
                "code_article": "7716704752",
                "description": "Page 1 sur 2 A livrer a WENDEL 7716704752 7738111040 6.000 572.82 1.000 41.21 2.000 23.12",
                "quantite": 20,
                "prix_unitaire_ht": 10151.54,
                "montant_ligne_ht": 2030.31,
            }
        ]
    )

    assert cleaned == []


def test_sanitize_order_lines_infers_quantity_from_price_total():
    cleaned = _sanitize_order_lines(
        [
            {
                "code_article": "7738111040",
                "description": "Regulateur ambiance",
                "quantite": None,
                "prix_unitaire_ht": 95.47,
                "montant_ligne_ht": 572.82,
            }
        ]
    )

    assert len(cleaned) == 1
    assert cleaned[0]["quantite"] == 6.0


def test_sanitize_order_lines_drops_swapped_qty_price_duplicate():
    cleaned = _sanitize_order_lines(
        [
            {
                "code_article": "7736507598",
                "description": "CHAUFFE EAU BOSCH THERM4300",
                "quantite": 12.0,
                "prix_unitaire_ht": 286.0,
                "montant_ligne_ht": 3432.0,
            },
            {
                "code_article": "7736505037",
                "description": "CHAUFFE EAU BOSCH THERM4300 / REMPLACE",
                "quantite": 286.0,
                "prix_unitaire_ht": 12.0,
                "montant_ligne_ht": 3432.0,
            },
        ]
    )
    assert len(cleaned) == 1
    assert cleaned[0]["code_article"] == "7736507598"
    assert cleaned[0]["quantite"] == 12.0
    llm_lines = [
        {
            "code_article": "7736504816",
            "quantite": 20.0,
            "montant_ligne_ht": 5500.0,
            "customer_reference": "24-002731",
        }
    ]
    deterministic_lines = [
        {
            "code_article": "7736504816",
            "quantite": 20.0,
            "montant_ligne_ht": 5500.0,
            "customer_reference": "24-002731",
        },
        {
            "code_article": "7736504816",
            "quantite": 10.0,
            "montant_ligne_ht": 2750.0,
            "customer_reference": "24-000025",
        },
    ]
    merged = _merge_order_line_candidates(llm_lines, deterministic_lines)
    assert len(merged) == 2
    assert merged[1]["quantite"] == 10.0
    assert merged[1]["customer_reference"] == "24-000025"


def test_system_health_payload_includes_ocr_status():
    from src.ai_status import build_system_health_payload

    payload = build_system_health_payload(
        {
            "api": {"ok": True},
            "database": {"ok": True},
            "masterdata": {"ok": True},
            "sftp_configured": False,
            "ocr": {
                "available": True,
                "version": "5.3.4",
                "lang": "fra+eng",
                "error": "",
            },
        }
    )
    assert payload["ocr"] == "connected"
    assert payload["ocrAvailable"] is True
    assert payload["ocrVersion"] == "5.3.4"
    assert payload["ocrLang"] == "fra+eng"
