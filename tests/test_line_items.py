from app.line_items import extract_line_items_from_lines
from app.line_items import extract_line_items_from_text


def test_extract_line_items_from_table_lines():
    lines = [
        "Code article Designation Quantite Prix unitaire Montant",
        "123456789 Widget premium 2 10,00 EUR 20,00 EUR",
        "Total HT 20,00 EUR",
    ]
    rows = extract_line_items_from_lines(lines)
    assert len(rows) >= 1
    assert rows[0]["article"] == "123456789"
    assert rows[0]["parser"] in {"table_lines", "table_line_regex"}


def test_extract_line_items_from_material_window_quantity_first():
    text = "2PCE MEGALIS ICONDENS NGVA IC 30-35 7736902448 1549,71€/ PCE"
    rows = extract_line_items_from_text(text, {"7736902448": "MEGALIS ICONDENS NGVA IC 30-35"})

    assert rows[0]["article"] == "7736902448"
    assert rows[0]["quantity"] == "2"
    assert rows[0]["unit"] == "PCE"
    assert rows[0]["unit_price"] == "1549,71"
    assert rows[0]["parser"] == "material_window"


def test_extract_line_items_from_multiline_split_rows():
    lines = [
        "Article",
        "7736504816",
        "PIECE       20,000     275,00",
        "275,00      5500,00",
        "Montant HT : EUR      8250,00",
    ]
    rows = extract_line_items_from_lines(lines)

    assert len(rows) >= 1
    assert rows[0]["article"] == "7736504816"
    assert rows[0]["quantity"] in {"20,000", "20.000", "20"}
    assert rows[0]["unit"] == "PCE"
    assert rows[0]["parser"] in {"multiline_window", "table_lines", "table_line_regex"}


def test_extract_line_items_from_table_lines_ignores_article_and_packaging_for_quantity():
    lines = [
        "Article  Designation  Colis  Qte  Unite  Prix unitaire  Montant",
        "123456789  Widget premium  10  2  PCE  10,00 EUR  20,00 EUR",
        "Total HT 20,00 EUR",
    ]

    rows = extract_line_items_from_lines(lines)

    assert len(rows) == 1
    assert rows[0]["article"] == "123456789"
    assert rows[0]["quantity"] == "2"
    assert rows[0]["unit"] == "PCE"


def test_extract_line_items_from_text_does_not_use_packaging_as_quantity():
    text = "10,00 EUR 20,00 EUR 01/01/2026 Widget premium 123456789 6"

    rows = extract_line_items_from_text(text, {})

    assert len(rows) == 1
    assert rows[0]["article"] == "123456789"
    assert rows[0]["quantity"] == ""
    assert rows[0]["parser"] == "compact_regex"
