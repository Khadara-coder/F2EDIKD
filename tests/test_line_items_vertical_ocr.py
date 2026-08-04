from app.line_items import extract_line_items_from_text


def test_vertical_ocr_article_blocks_keep_all_masterdata_articles():
    text = """
BALLON ECS STORA W 120-5 P1 B
      1,00
32/26
PIECE
      978,00      978,00
7735500779
 4092228
 ECO-PARTICIPATION DEEE
FRAIS
       18,00

KIT SONDE ECS POUR REGULATION EMS 2.0 LONGEUR
      1,00
32/26
PIECE
       19,80       19,80
7735502289
 4092228
"""
    materials = {
        "7735500779": "W 120-5 P1 B",
        "7735502289": "Kit sonde ECS NTC12K",
    }

    rows = extract_line_items_from_text(text, materials)

    assert [row["article"] for row in rows] == ["7735500779", "7735502289"]
    assert rows[0]["designation"] == "BALLON ECS STORA W 120-5 P1 B"
    assert rows[0]["unit_price"] == "978,00"
    assert rows[0]["amount"] == "978,00"
    assert rows[1]["designation"] == "KIT SONDE ECS POUR REGULATION EMS 2.0 LONGEUR"
    assert rows[1]["unit_price"] == "19,80"
    assert rows[1]["amount"] == "19,80"
