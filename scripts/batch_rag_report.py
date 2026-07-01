from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGRESSION_PDFS_DIR = ROOT / "data" / "regression" / "pdfs"
CORPUS_DIR = ROOT / "data" / "corpus" / "rag-purchase-orders"
sys.path.insert(0, str(ROOT))

from app.extraction import extract_candidate_fields
from app.server import pdf_pages_to_text


def score_delivery(detected: dict) -> int:
    status = detected.get("Statut", "")
    if status in {"Detectee", "Detectee par geometrie"}:
        score = 70
    elif status == "Libelle trouve mais adresse non reconstruite":
        return 25
    elif status == "Non detectee":
        return 0
    else:
        score = 40
    if detected.get("Code postal"):
        score += 15
    if detected.get("Ville"):
        score += 10
    if detected.get("Rue"):
        score += 5
    validation = detected.get("Validation code postal/ville") or {}
    if validation.get("match") is True:
        score += 10
    return min(100, score)


def score_shipto(validated: dict) -> int:
    status = (validated.get("Statut") or "").lower()
    if "validee master data" in status and validated.get("SHIPTO"):
        return 100
    if "validee master data" in status and validated.get("SOLDTO"):
        return 75
    if "a verifier" in status and validated.get("SOLDTO"):
        return 50
    if validated.get("SOLDTO") or validated.get("SHIPTO"):
        return 40
    if "master data indisponible" in status:
        return 0
    return 0


def score_order(document: dict, order_validation: dict | None) -> int:
    order = document.get("Numero de commande") or document.get("Commande detectee")
    if not order:
        return 0
    validation = order_validation or {}
    if validation.get("match") is True or document.get("Commande masterdata"):
        return 100
    if order:
        return 25
    return 0


def analyze_pdf(pdf_path: Path) -> dict:
    started = time.perf_counter()
    row: dict = {
        "fichier": pdf_path.name,
        "erreur": "",
        "source": "",
        "adresse_statut": "",
        "adresse_score": 0,
        "code_postal": "",
        "ville": "",
        "rue": "",
        "nom_service": "",
        "shipto_statut": "",
        "shipto_score": 0,
        "soldto": "",
        "shipto": "",
        "strategie": "",
        "raison_shipto": "",
        "commande": "",
        "commande_score": 0,
        "commande_masterdata": "",
        "lignes_count": 0,
        "lignes_score": 0,
        "duree_ms": 0,
    }
    try:
        payload = pdf_path.read_bytes()
        pages = pdf_pages_to_text(payload, "1")
        page = pages[0]
        text = page["text"]
        layout = page.get("layout") or {}
        row["source"] = page.get("source", "")

        fields = extract_candidate_fields(text, "Extraire adresse livraison", pdf_path.name, layout, {})
        structured = fields.get("structured") or {}
        detected = structured.get("adresses", {}).get("Adresse de livraison detectee") or {}
        validated = structured.get("adresses", {}).get("Adresse de livraison validee") or {}
        document = structured.get("document") or {}
        lines = structured.get("line_items") or []

        row["adresse_statut"] = detected.get("Statut", "")
        row["adresse_score"] = score_delivery(detected)
        row["code_postal"] = detected.get("Code postal") or ""
        row["ville"] = detected.get("Ville") or ""
        row["rue"] = detected.get("Rue") or ""
        row["nom_service"] = detected.get("Nom / service") or ""

        row["shipto_statut"] = validated.get("Statut", "")
        row["shipto_score"] = score_shipto(validated)
        row["soldto"] = validated.get("SOLDTO") or ""
        row["shipto"] = validated.get("SHIPTO") or ""
        row["strategie"] = validated.get("Strategie matching") or ""
        row["raison_shipto"] = validated.get("Raison") or ""

        row["commande"] = document.get("Numero de commande") or ""
        row["commande_masterdata"] = document.get("Commande masterdata") or ""
        order_validation = structured.get("validation", {}).get("commande") if isinstance(structured.get("validation"), dict) else None
        row["commande_score"] = score_order(document, order_validation if isinstance(order_validation, dict) else None)

        row["lignes_count"] = len(lines) if isinstance(lines, list) else 0
        row["lignes_score"] = min(100, int(row["lignes_count"] * 5)) if row["lignes_count"] else 0
    except Exception as exc:
        row["erreur"] = str(exc)[:500]
        row["adresse_score"] = 0
        row["shipto_score"] = 0
        row["commande_score"] = 0
        row["lignes_score"] = 0
        traceback.print_exc()
    row["duree_ms"] = int((time.perf_counter() - started) * 1000)
    return row


def write_markdown_summary(rows: list[dict], output_md: Path, *, title: str = "Rapport batch") -> None:
    total = len(rows)
    errors = sum(1 for row in rows if row["erreur"])
    shipto_ok = sum(1 for row in rows if row["shipto_score"] == 100)
    soldto_only = sum(1 for row in rows if row["shipto_score"] == 75)
    addr_ok = sum(1 for row in rows if row["adresse_score"] >= 70)
    no_client = sum(1 for row in rows if "non identifie" in (row["shipto_statut"] or "").lower())

    lines = [
        f"# {title}",
        "",
        f"- **Fichiers analysés** : {total}",
        f"- **Erreurs techniques** : {errors}",
        f"- **Adresse détectée (≥70 %)** : {addr_ok} ({round(100 * addr_ok / total, 1) if total else 0} %)",
        f"- **SHIPTO validé (100 %)** : {shipto_ok} ({round(100 * shipto_ok / total, 1) if total else 0} %)",
        f"- **SOLDTO sans SHIPTO (75 %)** : {soldto_only}",
        f"- **Client non identifié** : {no_client}",
        "",
        "## Synthèse par fichier",
        "",
        "| Fichier | Adr % | SHIPTO % | Cmd % | Lignes | CP | Ville | SOLDTO | SHIPTO | Statut SHIPTO |",
        "|---------|------:|---------:|------:|-------:|----|-------|--------|--------|---------------|",
    ]
    for row in sorted(rows, key=lambda item: (item["shipto_score"], item["adresse_score"])):
        lines.append(
            "| {fichier} | {adr} | {ship} | {cmd} | {lignes} | {cp} | {ville} | {soldto} | {shipto} | {statut} |".format(
                fichier=row["fichier"][:60].replace("|", "/"),
                adr=row["adresse_score"],
                ship=row["shipto_score"],
                cmd=row["commande_score"],
                lignes=row["lignes_count"],
                cp=row["code_postal"],
                ville=(row["ville"] or "")[:24].replace("|", "/"),
                soldto=row["soldto"],
                shipto=row["shipto"],
                statut=(row["shipto_statut"] or row["erreur"] or "")[:40].replace("|", "/"),
            )
        )

    lines.extend(
        [
            "",
            "## Échecs SHIPTO (client non identifié ou ambigu)",
            "",
        ]
    )
    for row in rows:
        if row["shipto_score"] < 100 and not row["erreur"]:
            lines.append(
                f"- **{row['fichier']}** — {row['code_postal']} {row['ville']} — {row['rue'][:60] if row['rue'] else ''} — {row['raison_shipto'] or row['shipto_statut']}"
            )

    output_md.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch analyse PDF bons de commande")
    parser.add_argument(
        "input_dir",
        type=Path,
        nargs="?",
        default=REGRESSION_PDFS_DIR,
        help=f"Dossier PDF (défaut : jeu de régression {REGRESSION_PDFS_DIR.relative_to(ROOT)})",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "regression_report.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "reports" / "regression_report.md")
    parser.add_argument("--title", type=str, default="Rapport batch — jeu de régression (30 PDF)")
    parser.add_argument("--limit", type=int, default=0, help="Limiter le nombre de PDF (0 = tous)")
    args = parser.parse_args()

    input_dir = args.input_dir
    if not input_dir.exists():
        raise SystemExit(f"Dossier introuvable : {input_dir}\nExécutez : .\\scripts\\build_regression_set.ps1")

    pdfs = sorted(
        {
            *input_dir.glob("*.pdf"),
            *input_dir.glob("*.PDF"),
        },
        key=lambda item: item.name.lower(),
    )
    if args.limit:
        pdfs = pdfs[: args.limit]

    print(f"Analyse de {len(pdfs)} PDF dans {input_dir}")
    rows = []
    for index, pdf_path in enumerate(pdfs, start=1):
        print(f"[{index}/{len(pdfs)}] {pdf_path.name}", flush=True)
        rows.append(analyze_pdf(pdf_path))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_summary(rows, args.markdown, title=args.title)

    # CSV for Excel
    csv_path = args.output.with_suffix(".csv")
    if rows:
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    print(f"JSON: {args.output}")
    print(f"Markdown: {args.markdown}")
    print(f"CSV: {csv_path}")


if __name__ == "__main__":
    main()
