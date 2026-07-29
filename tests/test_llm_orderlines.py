from app.engines.llm_orderlines import _cohere_line, _finalize_llm_lines


def test_cohere_line_infers_quantity_from_price_and_total():
    fixed = _cohere_line(
        {
            "code_article": "7738111040",
            "description": "Regulateur ambiance",
            "quantite": None,
            "prix_unitaire_ht": "95,47",
            "montant_ligne_ht": "572,82",
        }
    )

    assert fixed is not None
    assert fixed["quantite"] == 6.0
    assert fixed["prix_unitaire_ht"] == 95.47
    assert fixed["montant_ligne_ht"] == 572.82


def test_cohere_line_rejects_polluted_description_with_weak_signals():
    fixed = _cohere_line(
        {
            "code_article": "7716704752",
            "description": "A livrer a WENDEL DISTRIBUTION page 1 sur 2 9.000 6840.00 7716704752 7738111040 7738112343",
            "quantite": 0,
            "prix_unitaire_ht": "9",
            "montant_ligne_ht": "0",
        }
    )

    assert fixed is None


def test_finalize_llm_lines_rejects_polluted_batch():
    result = _finalize_llm_lines(
        [
            {
                "code_article": "7716704752",
                "description": "A livrer a WENDEL DISTRIBUTION page 1 sur 2 9.000 6840.00 7716704752 7738111040 7738112343",
                "quantite": 0,
                "prix_unitaire_ht": "9",
                "montant_ligne_ht": "0",
            },
            {
                "code_article": "7738111040",
                "description": "Regulateur ambiance",
                "quantite": None,
                "prix_unitaire_ht": "95,47",
                "montant_ligne_ht": "572,82",
            },
            {
                "code_article": "7738112343",
                "description": "Page 1 sur 2 1.000 41.21 7738112343 7716780194",
                "quantite": 0,
                "prix_unitaire_ht": "1",
                "montant_ligne_ht": "0",
            },
        ]
    )

    assert result == []