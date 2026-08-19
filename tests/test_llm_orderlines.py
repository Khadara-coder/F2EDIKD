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


def test_finalize_llm_lines_keeps_valid_lines_from_mixed_batch():
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

    assert len(result) == 1
    assert result[0]["code_article"] == "7738111040"


def test_split_text_for_llm_keeps_short_document_whole():
    from app.engines.llm_orderlines import _split_text_for_llm

    text = "Ligne " * 20
    assert _split_text_for_llm(text) == [text.strip()]


def test_split_text_for_llm_covers_all_pages():
    from app.engines.llm_orderlines import _split_text_for_llm

    pages = [f"===== PAGE {i} =====\nARTICLE{i:04d} DESC {i} 1,00 10,00" for i in range(1, 6)]
    text = "\n".join(pages)
    chunks = _split_text_for_llm(text, max_chars=80)
    joined = "\n".join(chunks)
    for i in range(1, 6):
        assert f"ARTICLE{i:04d}" in joined
    assert chunks


def test_llm_extract_orderlines_sends_full_document_not_truncated_head(monkeypatch):
    from app.engines import llm_orderlines as mod

    captured = []

    def fake_call(prompt, max_tokens=1500, endpoint=None):
        captured.append(prompt)
        if "7736505037" in prompt:
            return '[{"code_article":"7736505037","description":"VENTOUSE","quantite":1,"prix_unitaire_ht":393,"montant_ligne_ht":393}]'
        return '[{"code_article":"7709003079","description":"ROBINET","quantite":1,"prix_unitaire_ht":31.61,"montant_ligne_ht":31.61}]'

    monkeypatch.setattr(mod, "_call_llm", fake_call)
    head = "A" * 4500
    tail = "===== PAGE 2 =====\n7736505037 CHAUFFE EAU VENTOUSE 1,00 393,00"
    lines = mod.llm_extract_orderlines(head + "\n" + tail)
    assert captured
    assert any("7736505037" in prompt for prompt in captured)
    assert any(line["code_article"] == "7736505037" for line in lines)