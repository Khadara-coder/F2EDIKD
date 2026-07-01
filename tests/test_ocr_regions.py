from app.ocr_regions import merge_page_layouts, merge_page_text, needs_selective_ocr, selective_crop_box


def test_needs_selective_ocr_when_sparse():
    assert needs_selective_ocr("abc", None) is True


def test_needs_selective_ocr_when_missing_delivery_signals():
    text = "Bon de commande fournisseur XYZ total ht 100,00"
    assert needs_selective_ocr(text, {"lines": [{"text": "Bon de commande fournisseur XYZ"}]}) is True


def test_selective_crop_defaults_to_top_band():
    box = selective_crop_box(1000, 2000, None)
    assert box == (0, 0, 1000, 1100)


def test_selective_crop_around_delivery_anchor():
    layout = {
        "width": 500,
        "height": 800,
        "lines": [
            {"text": "Adresse de livraison", "bbox": {"x0": 40, "y0": 180, "x1": 220, "y1": 200}},
        ],
    }
    box = selective_crop_box(1000, 1600, layout)
    left, top, right, bottom = box
    assert left < 100
    assert top < 400
    assert right > 400
    assert bottom > top


def test_merge_page_text_deduplicates():
    assert merge_page_text("Bon de commande", "Bon de commande\nAdresse de livraison") == "Bon de commande\nAdresse de livraison"


def test_merge_page_layouts_reinjects_crop_offsets():
    base_layout = {"source": "pdf_text", "width": 500, "height": 800, "lines": []}
    crop_layout = {
        "source": "ocr",
        "width": 300,
        "height": 200,
        "lines": [
            {
                "text": "Adresse OCR",
                "bbox": {"x0": 20, "y0": 30, "x1": 80, "y1": 50},
            }
        ],
    }

    merged = merge_page_layouts(base_layout, crop_layout, (200, 100, 500, 300), render_scale=2.0)
    bbox = merged["lines"][0]["bbox"]

    assert bbox == {"x0": 110.0, "y0": 65.0, "x1": 140.0, "y1": 75.0}
