#!/usr/bin/env python3
"""Batch runner for GenieCommande / File2EDI via Docker Compose API.

Usage:
    python scripts/run_batch_docker_test.py --limit 10
    python scripts/run_batch_docker_test.py --all
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests
from tqdm import tqdm

DEFAULT_API_URL = "http://localhost:8080/api"
DEFAULT_USER = "khadara"
DEFAULT_PASS = "admin123"
DEFAULT_PDF_DIR = "RAG Purchase Orders"
REPORTS_DIR = Path("reports")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run batch test on PDFs via Docker Compose API")
    parser.add_argument("--limit", type=int, default=10, help="Number of PDFs to test (default: 10)")
    parser.add_argument("--all", action="store_true", help="Process all available PDFs")
    parser.add_argument("--workers", type=int, default=1, help="Number of concurrent worker threads (default: 1)")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help=f"API base URL (default: {DEFAULT_API_URL})")
    parser.add_argument("--user", default=DEFAULT_USER, help=f"Admin username (default: {DEFAULT_USER})")
    parser.add_argument("--password", default=DEFAULT_PASS, help=f"Admin password (default: {DEFAULT_PASS})")
    parser.add_argument("--dir", default=DEFAULT_PDF_DIR, help=f"PDF directory (default: {DEFAULT_PDF_DIR})")
    parser.add_argument("--output", default=None, help="Output JSON report file")
    return parser.parse_args()


def get_authenticated_session(api_url: str, user: str, password: str) -> requests.Session:
    session = requests.Session()
    login_url = f"{api_url}/auth/login"
    res = session.post(login_url, json={"username": user, "password": password}, timeout=15)
    if res.status_code != 200:
        raise RuntimeError(f"Login failed ({res.status_code}): {res.text}")
    return session


def process_single_pdf(session: requests.Session, api_url: str, pdf_path: Path) -> dict[str, Any]:
    start_time = time.perf_counter()
    file_name = pdf_path.name
    file_size = pdf_path.stat().st_size

    result_record: dict[str, Any] = {
        "fileName": file_name,
        "filePath": str(pdf_path),
        "fileSize": file_size,
        "success": False,
        "uploadId": None,
        "orderId": None,
        "po_number": None,
        "order_date": None,
        "client_name": None,
        "delivery_address": None,
        "line_count": 0,
        "total_amount": 0.0,
        "status": "ERROR",
        "elapsed_s": 0.0,
        "error": None,
        "anomalies": [],
    }

    try:
        # Step 1: Upload
        with open(pdf_path, "rb") as fh:
            upload_res = session.post(
                f"{api_url}/upload",
                files={"pdf": (file_name, fh, "application/pdf")},
                timeout=30,
            )

        if upload_res.status_code != 200:
            result_record["error"] = f"Upload failed ({upload_res.status_code}): {upload_res.text[:200]}"
            result_record["elapsed_s"] = round(time.perf_counter() - start_time, 2)
            return result_record

        upload_id = upload_res.json().get("uploadId")
        result_record["uploadId"] = upload_id

        # Step 2: Extract
        extract_res = session.post(f"{api_url}/upload/{upload_id}/extract", timeout=60)
        if extract_res.status_code != 200:
            result_record["error"] = f"Extract failed ({extract_res.status_code}): {extract_res.text[:200]}"
            result_record["elapsed_s"] = round(time.perf_counter() - start_time, 2)
            return result_record

        ext_data = extract_res.json()
        order_id = ext_data.get("orderId")
        result_record["orderId"] = order_id
        result_record["po_number"] = ext_data.get("customerOrderNumber")
        result_record["order_date"] = ext_data.get("orderDate")
        result_record["client_name"] = ext_data.get("clientName")
        result_record["delivery_address"] = ext_data.get("deliveryAddress")
        result_record["line_count"] = ext_data.get("lineCount", 0)
        result_record["total_amount"] = ext_data.get("totalAmount", 0.0)

        # Step 3: Fetch review details for status and anomalies
        review_res = session.get(f"{api_url}/orders/{order_id}/review", timeout=15)
        if review_res.status_code == 200:
            review_data = review_res.json()
            order_info = review_data.get("order", {})
            result_record["status"] = order_info.get("status", "OK")
            result_record["confidence"] = order_info.get("globalConfidence", 0)
            result_record["anomalies"] = [
                a.get("fieldName") or a.get("message") for a in review_data.get("anomalies", [])
            ]
        else:
            result_record["status"] = "OK"

        result_record["success"] = True

    except Exception as exc:
        result_record["error"] = str(exc)

    result_record["elapsed_s"] = round(time.perf_counter() - start_time, 2)
    return result_record


def main() -> None:
    args = parse_args()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Discover PDFs
    pattern = os.path.join(args.dir, "*.pdf")
    all_pdfs = sorted(Path(p) for p in glob.glob(pattern))

    if not all_pdfs:
        print(f"❌ Aucun fichier PDF trouvé dans '{args.dir}'")
        sys.exit(1)

    total_available = len(all_pdfs)
    selected_pdfs = all_pdfs if args.all else all_pdfs[: args.limit]
    total_to_process = len(selected_pdfs)

    print(f"\n========================================================")
    print(f" 🚀 GenieCommande / File2EDI — Test Docker Compose")
    print(f"========================================================")
    print(f" • API URL      : {args.api_url}")
    print(f" • Utilisateur  : {args.user}")
    print(f" • Fichiers     : {total_to_process} / {total_available} disponibles")
    print(f"========================================================\n")

    # 2. Check health & authenticate
    try:
        health = requests.get(f"{args.api_url}/health/system", timeout=10).json()
        print(f"✅ Santé du système Docker:")
        print(f"   - API: {health.get('api')}, DB: {health.get('database')}, OCR: {health.get('ocr')}, AI: {health.get('ai')}\n")
    except Exception as exc:
        print(f"❌ Impossible de joindre l'API sur {args.api_url}: {exc}")
        sys.exit(1)

    print("🔐 Authentification en cours...")
    try:
        session = get_authenticated_session(args.api_url, args.user, args.password)
        print("✅ Authentification réussie !\n")
    except Exception as exc:
        print(f"❌ Erreur d'authentification: {exc}")
        sys.exit(1)

    # 3. Process files with progress bar
    results: list[dict[str, Any]] = []
    success_count = 0
    error_count = 0

    print(f"▶️ Début du traitement des {total_to_process} PDFs (workers={args.workers})...\n")

    if args.workers > 1:
        import concurrent.futures

        pbar = tqdm(total=total_to_process, desc="Traitement PDFs", unit="pdf", ncols=100)

        # Thread-local sessions
        def _worker_task(pdf_p: Path) -> dict[str, Any]:
            thread_session = get_authenticated_session(args.api_url, args.user, args.password)
            return process_single_pdf(thread_session, args.api_url, pdf_p)

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(_worker_task, p): p for p in selected_pdfs}
            for future in concurrent.futures.as_completed(futures):
                res = future.result()
                results.append(res)
                if res["success"]:
                    success_count += 1
                    po_display = res['po_number'] or 'N/A'
                    pbar.set_postfix_str(f"✅ PO: {po_display} ({res['elapsed_s']}s)")
                else:
                    error_count += 1
                    pbar.set_postfix_str(f"❌ Erreur ({res['elapsed_s']}s)")
                pbar.update(1)
        pbar.close()
    else:
        pbar = tqdm(selected_pdfs, desc="Traitement PDFs", unit="pdf", ncols=100)
        for pdf_path in pbar:
            display_name = pdf_path.name[:30] + "..." if len(pdf_path.name) > 33 else pdf_path.name
            pbar.set_postfix_str(f"En cours: {display_name}")

            res = process_single_pdf(session, args.api_url, pdf_path)
            results.append(res)

            if res["success"]:
                success_count += 1
                po_display = res['po_number'] or 'N/A'
                pbar.set_postfix_str(f"✅ PO: {po_display} ({res['elapsed_s']}s)")
            else:
                error_count += 1
                pbar.set_postfix_str(f"❌ Erreur ({res['elapsed_s']}s)")

        pbar.close()

    # 4. Generate Summary
    total_time = sum(r["elapsed_s"] for r in results)
    avg_time = round(total_time / len(results), 2) if results else 0

    status_counts: dict[str, int] = {}
    for r in results:
        st = r["status"]
        status_counts[st] = status_counts.get(st, 0) + 1

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    out_file = Path(args.output) if args.output else REPORTS_DIR / f"docker_batch_test_{total_to_process}files_{timestamp_str}.json"

    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_processed": total_to_process,
                "total_available": total_available,
                "success_count": success_count,
                "error_count": error_count,
                "total_time_s": round(total_time, 2),
                "avg_time_s": avg_time,
                "status_distribution": status_counts,
                "results": results,
            },
            fh,
            indent=2,
            ensure_ascii=False,
        )

    print(f"\n========================================================")
    print(f" 📊 Bilan du test ({total_to_process} fichiers traités)")
    print(f"========================================================")
    print(f" • Succès API      : {success_count} / {total_to_process} ({round(success_count / total_to_process * 100, 1)}%)")
    print(f" • Échecs HTTP     : {error_count} / {total_to_process}")
    print(f" • Temps total     : {round(total_time, 2)}s (moyenne: {avg_time}s / PDF)")
    print(f" • Répartition des statuts métier:")
    for st, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"    - {st:20s} : {count}")
    print(f"\n📁 Rapport détaillé sauvegardé dans : {out_file}")
    print(f"========================================================\n")


if __name__ == "__main__":
    main()
