from app.amounts import find_label_amount, rank_amounts_by_context


def test_find_label_amount_same_line():
    text = "Total TTC : 1 234,56 EUR"
    assert find_label_amount(text, "Total TTC") == "1 234,56 EUR"


def test_find_label_amount_next_line():
    text = "Total TTC\n1 234,56 EUR\n"
    assert find_label_amount(text, "Total TTC") == "1 234,56 EUR"


def test_rank_amounts_prefers_total_ttc_proximity():
    text = """
    Article A 10,00 EUR
    Article B 20,00 EUR
    Total TTC
    30,00 EUR
    """
    ranked = rank_amounts_by_context(text, ["10,00 EUR", "20,00 EUR", "30,00 EUR"])
    assert ranked[0]["montant"] == "30,00 EUR"
    assert ranked[0]["raison"] == "under_total_ttc"
