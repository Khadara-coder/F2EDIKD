from app.line_items import extract_line_items, extract_line_items_from_text


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


def test_elm_supplier_order_reads_all_pages_and_ignores_replacement_refs():
    text = """
BON DE COMMANDE FOURNISSEUR D U P L I C A T A
87020002940 MANETTE PIECE 1,000 8,65 4,41 4,41
ELM / BOSCH : 87020002940
Remises : 49.00%
8738724269 CONTROLE EVACUATION GAZ BRULES PIECE 1,000 65,00 33,15 33,15
REMPLACE 87072064550
Page 2
871861054A0 CIRCULATEUR PIECE 1,000 361,00 184,11 184,11
Page 3
87168356070 ELECTRODE D'IONISATION PIECE 3,000 29,00 14,79 44,37
Page 4
87186649200 JEU D'ELECTRODES PIECE 2,000 90,00 45,90 91,80
REMPLACE 87181070890
"""

    # A populated page-1 layout must not truncate the multi-page text parser.
    layout = {
        "source": "pdf_text",
        "lines": [
            {
                "text": "87020002940 MANETTE PIECE 1,000 8,65 4,41 4,41",
                "bbox": {"x0": 0, "y0": 0, "x1": 100, "y1": 10},
            }
        ],
    }
    rows = extract_line_items(text, layout, {})

    assert [row["article"] for row in rows] == [
        "87020002940",
        "8738724269",
        "871861054A0",
        "87168356070",
        "87186649200",
    ]
    assert rows[0]["quantity"] == "1"
    assert rows[0]["unit_price"] == "4,41"
    assert rows[0]["amount"] == "4,41"
    assert rows[3]["quantity"] == "3"
    assert rows[3]["amount"] == "44,37"


def test_elm_supplier_order_reads_pymupdf_split_rows():
    text = """
BON DE COMMANDE FOURNISSEUR
87020002940
MANETTE
PIECE        1,000      8,65
      4,41         4,41
ELM / BOSCH : 87020002940
REMPLACE 87020000000
871861054A0
CIRCULATEUR
PIECE        1,000    361,00
    184,11       184,11
87168371260
CIRCULAT.SAN.GRUNDFOS UPO 15-30/130 CIL2PIECE        1,000    230,00
    117,30       117,30
"""

    rows = extract_line_items(text, None, {})

    assert [row["article"] for row in rows] == [
        "87020002940",
        "871861054A0",
        "87168371260",
    ]
    assert rows[0]["designation"] == "MANETTE"
    assert rows[0]["quantity"] == "1"
    assert rows[0]["unit_price"] == "4,41"
    assert rows[1]["amount"] == "184,11"
    assert rows[2]["designation"].endswith("CIL2")
    assert rows[2]["amount"] == "117,30"
