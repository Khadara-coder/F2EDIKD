#!/usr/bin/env python3
"""
Test de 50 documents aléatoires - RAG Purchase Orders
Évalue la qualité d'extraction sur un échantillon réel des améliorations Phase 1+2.

Usage (dans le container):
  python scripts/test_random_pdfs.py

Usage local (avec le dossier monté):
  python scripts/test_random_pdfs.py --source "RAG Purchase Orders"
"""
import sys
import os
import random
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

RAG_DIR_DEFAULT = Path(__file__).parent.parent / "RAG Purchase Orders"
N_SAMPLE = 50
SEED = 42  # reproductible

# ─── champs à évaluer ────────────────────────────────────────────────────────
FIELDS = [
    "numero_commande",
    "date_commande",
    "numero_client",
    "total_ht",
]
LINE_FIELDS = [
    "code_article",
    "quantite",
    "prix_unitaire_ht",
    "montant_ligne_ht",
    "customer_reference",
    "payment_terms",
    "date_livraison",
    "special_instructions",
]


def extract_pdf(pdf_path: Path) -> dict | None:
    """Run the full extraction pipeline on a single PDF."""
    try:
        from app.pdf_reader import pdf_pages_to_text
        from app.ocr import ocr_image_with_layout
        from app.extraction import extract_candidate_fields
        
        with open(pdf_path, "rb") as fh:
            payload = fh.read()
        
        pages = pdf_pages_to_text(payload, "1", ocr_with_layout=ocr_image_with_layout)
        if not pages:
            return {"error": "empty_text", "file": pdf_path.name}
        
        text   = pages[0].get("text") or ""
        layout = pages[0].get("layout")
        if not text.strip():
            return {"error": "empty_text", "file": pdf_path.name}
        
        fields = extract_candidate_fields(text, "", pdf_path.name, layout, {})
        structured = fields.get("structured", {})
        return structured
    except Exception as e:
        return {"error": str(e)[:80], "file": pdf_path.name}


def score_header(result: dict) -> dict:
    """Check header fields quality."""
    doc = result.get("document") or {}
    montants = result.get("montants") or {}
    adresses = result.get("adresses") or {}
    validated = adresses.get("Adresse de livraison validee") or {}
    scores = {
        "numero_commande": bool(doc.get("Numero de commande")),
        "date_commande": bool(doc.get("Date commande LLM") or doc.get("Date document")),
        "numero_client": bool(validated.get("SOLDTO") or validated.get("name")),
        "total_ht": bool(montants.get("Total HT")),
    }
    return scores


def score_lines(result: dict) -> dict:
    """Score quality of line items extraction."""
    lines_data = result.get("lignes_commande") or {}
    lines = lines_data.get("lignes") or []
    
    if not lines:
        return {"n_lines": 0, "fields": {f: 0 for f in LINE_FIELDS}}
    
    field_counts = {f: 0 for f in LINE_FIELDS}
    for line in lines:
        for f in LINE_FIELDS:
            # Map standardized field names to actual keys in the result
            actual_keys = {
                "code_article": ["code_article", "article"],
                "quantite": ["quantite", "quantity"],
                "prix_unitaire_ht": ["prix_unitaire_ht", "unit_price"],
                "montant_ligne_ht": ["montant_ligne_ht", "amount"],
                "customer_reference": ["customer_reference", "ref_client"],
                "payment_terms": ["payment_terms"],
                "date_livraison": ["date_livraison", "delivery_date"],
                "special_instructions": ["special_instructions"],
            }
            val = None
            for key in actual_keys.get(f, [f]):
                val = line.get(key)
                if val is not None:
                    break
            if val is not None and str(val).strip() not in ("None", "", "0", "0.0"):
                field_counts[f] += 1
    
    field_rates = {f: round(field_counts[f] / len(lines), 2) for f in LINE_FIELDS}
    return {"n_lines": len(lines), "fields": field_rates}


def main(source_dir: Path):
    random.seed(SEED)
    
    # Find all PDFs (case-insensitive)
    all_pdfs = [p for p in source_dir.iterdir() if p.suffix.lower() == ".pdf"]
    
    if len(all_pdfs) < N_SAMPLE:
        print(f"⚠  Seulement {len(all_pdfs)} PDFs trouvés - test sur tous")
        sample = all_pdfs
    else:
        sample = random.sample(all_pdfs, N_SAMPLE)
    
    sample.sort(key=lambda p: p.name)
    
    print(f"\n{'='*65}")
    print(f"TEST EXTRACTION - {N_SAMPLE} PDFs ALÉATOIRES")
    print(f"Source: {source_dir}")
    print(f"Seed:   {SEED}  |  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*65}\n")
    
    results = []
    errors = []
    total_lines = 0
    
    field_totals = {f: 0 for f in FIELDS}
    line_field_totals = {f: 0.0 for f in LINE_FIELDS}
    docs_with_lines = 0
    
    for i, pdf in enumerate(sample, 1):
        t0 = time.time()
        result = extract_pdf(pdf)
        elapsed = time.time() - t0
        
        if not result or "error" in result:
            err = result.get("error", "unknown") if result else "None returned"
            errors.append(pdf.name)
            print(f"  [{i:02d}/{N_SAMPLE}] ✗  {pdf.name[:55]:<55}  ERR: {err[:30]}")
            continue
        
        h_scores = score_header(result)
        l_scores = score_lines(result)
        
        n_lines = l_scores["n_lines"]
        total_lines += n_lines
        
        h_ok = sum(h_scores.values())
        
        # Update totals
        for f, ok in h_scores.items():
            if ok:
                field_totals[f] += 1
        
        if n_lines > 0:
            docs_with_lines += 1
            for f, rate in l_scores["fields"].items():
                line_field_totals[f] += rate
        
        # Per-line quality indicators
        qty_ok = l_scores["fields"].get("quantite", 0)
        ref_ok = l_scores["fields"].get("customer_reference", 0)
        pay_ok = l_scores["fields"].get("payment_terms", 0)
        date_ok = l_scores["fields"].get("date_livraison", 0)
        
        status = "✓" if h_ok >= 2 and n_lines > 0 else "⚠"
        
        results.append({
            "file": pdf.name,
            "header": h_scores,
            "lines": l_scores,
            "elapsed_s": round(elapsed, 2),
        })
        
        print(
            f"  [{i:02d}/{N_SAMPLE}] {status}  {pdf.name[:50]:<50}"
            f"  L:{n_lines:2d}  H:{h_ok}/4"
            f"  Qty:{qty_ok:.0%}  Ref:{ref_ok:.0%}  Pay:{pay_ok:.0%}  Dlv:{date_ok:.0%}"
            f"  ({elapsed:.1f}s)"
        )
    
    # ─── SUMMARY ─────────────────────────────────────────────────────────────
    n_ok = len(results)
    n_err = len(errors)
    
    print(f"\n{'='*65}")
    print(f"RÉSUMÉ - {n_ok}/{N_SAMPLE} documents traités ({n_err} erreurs)")
    print(f"{'='*65}")
    
    if n_ok == 0:
        print("  Aucun document traité avec succès.")
        return
    
    # Header fields
    print(f"\n  [CHAMPS ENTÊTE]")
    for f in FIELDS:
        rate = round(field_totals[f] / n_ok * 100)
        bar = "█" * (rate // 5) + "░" * (20 - rate // 5)
        print(f"    {f:<30}  [{bar}]  {rate:3d}%  ({field_totals[f]}/{n_ok})")
    
    # Line fields
    print(f"\n  [CHAMPS LIGNES COMMANDE] (sur {docs_with_lines} docs avec lignes, {total_lines} lignes au total)")
    for f in LINE_FIELDS:
        if docs_with_lines > 0:
            avg = round(line_field_totals[f] / docs_with_lines * 100)
        else:
            avg = 0
        bar = "█" * (avg // 5) + "░" * (20 - avg // 5)
        
        # Highlight Phase 1+2 improvements
        tag = ""
        if f in ("customer_reference", "payment_terms"):
            tag = "  ← Phase 1 NEW"
        elif f in ("date_livraison", "special_instructions"):
            tag = "  ← Phase 2 NEW"
        
        print(f"    {f:<30}  [{bar}]  {avg:3d}%{tag}")
    
    # Errors
    if errors:
        print(f"\n  [ERREURS ({n_err})]")
        for e in errors:
            print(f"    ✗  {e}")
    
    # Perf
    total_time = sum(r["elapsed_s"] for r in results)
    print(f"\n  Temps total: {total_time:.1f}s  |  Moy: {total_time/n_ok:.1f}s/doc")
    
    # Save results JSON
    output_path = Path(__file__).parent.parent / "reports" / f"random_pdf_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fp:
        json.dump({
            "sample_size": N_SAMPLE,
            "seed": SEED,
            "date": datetime.now().isoformat(),
            "processed": n_ok,
            "errors": n_err,
            "header_rates": {f: round(field_totals[f]/n_ok*100) for f in FIELDS},
            "line_rates": {f: round(line_field_totals[f]/max(1,docs_with_lines)*100) for f in LINE_FIELDS},
            "results": results,
            "error_files": errors,
        }, fp, indent=2, ensure_ascii=False)
    
    print(f"\n  Rapport JSON: {output_path.name}")
    print(f"{'='*65}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        default=str(RAG_DIR_DEFAULT),
        help="Chemin vers le dossier des PDFs",
    )
    parser.add_argument("--n", type=int, default=N_SAMPLE, help="Nombre de PDFs")
    parser.add_argument("--seed", type=int, default=SEED, help="Seed aléatoire")
    args = parser.parse_args()
    
    N_SAMPLE = args.n
    SEED = args.seed
    
    source = Path(args.source)
    if not source.exists():
        print(f"❌  Dossier introuvable: {source}")
        sys.exit(1)
    
    main(source)
