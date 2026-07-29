from app.extraction import _choose_final_date, _finalize_document_totals


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