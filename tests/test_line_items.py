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
