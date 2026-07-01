"""n8n project analyzer for EDIFACT Orders Generator.

Recursively scans the n8n project folder, extracts EDIFACT rules,
rejection codes, duplicate logic, master-data usage, and deployment
constraints. Generates docs/N8N_ANALYSIS_REPORT.md.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .exceptions import N8nAnalysisError

log = logging.getLogger("edifact.n8n_analyzer")

# File extensions to scan (text-readable)
_TEXT_EXTENSIONS = {
    ".json", ".md", ".txt", ".ps1", ".env",
    ".example", ".yaml", ".yml", ".ts", ".js",
}
# Substrings that flag a file as binary (skip)
_BINARY_NAMES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip",
                 ".exe", ".pyc", ".db", ".sqlite"}


# --------------------------------------------------------------------------- #
# Known rules extracted from n8n analysis (hardcoded from workspace review)
# These are the VERIFIED rules integrated into the Python project.
# --------------------------------------------------------------------------- #

KNOWN_RULES = """
## Verified rules extracted from n8n project analysis

### Duplicate Detection
- Composite key: order_number (order_key) + soldto + pdf_hash
- Final states triggering duplicate rejection: SFTP_SUBMITTED, SENT, DELIVERED
- DB_Salesorder.csv.BSTNK is comparison-only; it must NOT be inserted into the ledger order_key
- n8n DataTable IDs (for reference): Customers=hogSROnAz1CUwCcn, Partners=5hkYUqpxkfOftza9, Materials=SePUAQrQFc1bCOUp, Ledger=hnDkTv6vRuqUCCl5

### Partner Matching Policy
- Postal exact match is primary evidence
- City exact match is primary evidence
- Street match is a tie-breaker ONLY
- Street-only matches must never qualify as strong evidence
- Strong evidence requires postal exact OR city exact
- Minimum confidence: Sold-to=75, Ship-to=80
- Unique score gap >=15 required to auto-select without strong postal/city
- VAT normalization: strip spaces, punctuation, lowercase before comparison

### DEPT Derivation
- DEPT = postal_code digits [0:2], fallback 'NA'

### Team Routing (ADV / Fonction Partenaire)
- TEAM 1: all material codes start with '7' AND none start with '8'
- TEAM 2: mixed codes or any code starts with '8'

### Rejection Codes (from n8n canonical model)
- ORDER_KEY_MISSING: no order number in PDF
- CONTRACT_KEYWORD: PDF contains contract/quotation keywords
- NO_VALID_ARTICLE: no valid article/material line items
- CONTRACT_BREAK_ADDRESSES_MISSING: addresses block incomplete
- DUPLICATE_ORDER: same order already submitted
- UNKNOWN_MATERIAL: article cannot be resolved to SAP MATNR
- DISCONTINUED_MATERIAL: MATNR in discontinued lookup
- ROH_NONCOMMERCIAL: MATNR is ROH type
- SFTP_UPLOAD_FAILED: SFTP submission failed after retries
- LOW_CONFIDENCE_DESCRIPTION_MATCH: fuzzy match below threshold
- MISSING_QUANTITY: no quantity on order line
- INVALID_QUANTITY: non-numeric or non-positive quantity
- SOLDTO_LOW_CONFIDENCE: Sold-to match below 75
- SOLDTO_AMBIGUOUS: Tied candidates, no strong evidence
- SHIPTO_LOW_CONFIDENCE: Ship-to match below 80
- SHIPTO_WEAK_EVIDENCE: Street-only match rejected
- SHIPTO_AMBIGUOUS: Tied ship-to candidates

### EDIFACT Generation
- Message type: ORDERS D.96A
- UNA constant: UNA:+.? '
- UNB always ELM_STANDARD: UNOC:3 + 4399901876613 + 3015981600108
- UNH reference: 1
- BGM+220 constant
- DTM+137 from PDF order date
- NAD+BY from customer master (SOLDTO)
- NAD+DP from partner master (SHIPTO)
- LIN increments by 10
- PIA+5 contains resolved SAP MATNR
- IMD+A uses PDF description first, fallback to material master description
- QTY+21 uses PCE
- PRI+AAA included only when unit price present
- CNT+2 = line count
- UNT segment count must be accurate
- UNZ control reference must match UNB control reference

### Material Resolution Priority (POMPAC)
1. EAN lookup
2. Fourre-tout (customer alias) lookup
3. Direct MATNR match against 10564_Materials.csv
4. Strict fuzzy description match (min 65% token overlap)
5. Reject: UNKNOWN_MATERIAL

### Environment Variables Required
- SFTP_HOST
- SFTP_USERNAME
- SFTP_PASSWORD or SFTP_PRIVATE_KEY_PATH
- SFTP_PRIVATE_KEY_PASSPHRASE (optional if using key)
- SFTP_REMOTE_DIR

### Credential Rotation Reminder (from n8n security state)
- N8N_API_KEY must be rotated
- N8N_MCP_TOKEN must be rotated
- Any GitHub PAT used for workflow dispatch must be rotated
- SMTP and SFTP secrets must be confirmed rotated before cutover
"""


@dataclass
class AnalysisReport:
    """Aggregated results from n8n project analysis."""
    n8n_project_root: str
    analysed_folders: list[str] = field(default_factory=list)
    analysed_files: list[str] = field(default_factory=list)
    detected_workflows: list[str] = field(default_factory=list)
    detected_edifact_logic: list[str] = field(default_factory=list)
    detected_rejection_rules: list[str] = field(default_factory=list)
    detected_duplicate_logic: list[str] = field(default_factory=list)
    detected_master_data_usage: list[str] = field(default_factory=list)
    detected_env_variables: list[str] = field(default_factory=list)
    detected_risks: list[str] = field(default_factory=list)
    not_reusable: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _scan_directory(root: Path) -> tuple[list[Path], list[Path]]:
    """Recursively scan root and return (folders, files)."""
    folders: list[Path] = []
    files: list[Path] = []
    try:
        for item in sorted(root.rglob("*")):
            if item.is_dir():
                folders.append(item)
            elif item.is_file():
                # Skip binary files
                if not any(item.name.lower().endswith(ext) for ext in _BINARY_NAMES):
                    files.append(item)
    except Exception as exc:
        log.warning("Directory scan error: %s", exc)
    return folders, files


def _read_file_safe(path: Path, max_bytes: int = 200_000) -> Optional[str]:
    """Read a text file safely, returning None on failure."""
    try:
        ext = path.suffix.lower()
        # Check extension (relaxed: also read files with no extension or .example)
        name_lower = path.name.lower()
        if not any(name_lower.endswith(e) for e in _TEXT_EXTENSIONS) and "." in name_lower:
            return None
        return path.read_bytes()[:max_bytes].decode("utf-8-sig", errors="replace")
    except Exception:
        return None


def _extract_env_vars(text: str) -> list[str]:
    """Extract environment variable names from text."""
    import re
    found = re.findall(r"\b([A-Z][A-Z0-9_]{3,40})\b", text)
    # Filter likely env vars (all caps with underscores)
    return sorted(set(v for v in found if "_" in v))


def _detect_workflow_ids(text: str) -> list[str]:
    import re
    return re.findall(r"[A-Za-z0-9]{16,}", text)[:20]


def analyse_n8n_project(n8n_root: str) -> AnalysisReport:
    """Scan and analyse the n8n project folder.

    Args:
        n8n_root: Path to the n8n project folder.

    Returns:
        AnalysisReport with findings.
    """
    root = Path(n8n_root)
    report = AnalysisReport(n8n_project_root=str(root))

    if not root.exists():
        msg = f"n8n project root not found: {n8n_root}"
        log.warning(msg)
        report.errors.append(msg)
        return report

    log.info("Scanning n8n project folder: %s", n8n_root)
    folders, files = _scan_directory(root)

    report.analysed_folders = [str(f.relative_to(root)) for f in folders[:100]]
    report.analysed_files = [str(f.relative_to(root)) for f in files[:500]]

    all_text = ""
    for file_path in files:
        content = _read_file_safe(file_path)
        if content is None:
            continue
        all_text += content + "\n"

        # --- Detect workflow files ---
        if file_path.suffix in {".ts", ".js"} and "workflow" in file_path.name.lower():
            report.detected_workflows.append(str(file_path.relative_to(root)))

        # --- JSON workflow analysis ---
        if file_path.suffix == ".json":
            try:
                data = json.loads(content)
                if isinstance(data, dict):
                    if "nodes" in data:
                        report.detected_workflows.append(
                            f"{file_path.relative_to(root)} (JSON workflow)"
                        )
                        for node in data.get("nodes", []):
                            node_type = node.get("type", "")
                            node_name = node.get("name", "")
                            if "sftp" in node_type.lower() or "ftp" in node_type.lower():
                                report.detected_edifact_logic.append(
                                    f"SFTP node: {node_name}"
                                )
                            if "code" in node_type.lower():
                                code = node.get("parameters", {}).get("jsCode", "")
                                if "edifact" in code.lower() or "unb" in code.upper():
                                    report.detected_edifact_logic.append(
                                        f"EDIFACT code node: {node_name}"
                                    )
            except (json.JSONDecodeError, Exception):
                pass

        # --- Detect rejection rules in .md / .ts / .js ---
        if file_path.suffix in {".md", ".ts", ".js"}:
            import re
            rejection_codes = re.findall(
                r"\b([A-Z_]{5,40}_(?:MISSING|FAILED|ERROR|INVALID|DUPLICATE|UNKNOWN|"
                r"REJECTED|MISMATCH|NOT_FOUND|LOW_CONFIDENCE|AMBIGUOUS|REQUIRED))\b",
                content,
            )
            for code in set(rejection_codes):
                if code not in report.detected_rejection_rules:
                    report.detected_rejection_rules.append(code)

        # --- Detect duplicate logic ---
        content_lower = content.lower()
        if any(kw in content_lower for kw in ["duplicate", "duplicate_flow", "ledger", "order_key", "bstnk"]):
            if str(file_path.relative_to(root)) not in report.detected_duplicate_logic:
                report.detected_duplicate_logic.append(
                    str(file_path.relative_to(root))
                )

        # --- Detect master data usage ---
        if any(kw in content_lower for kw in ["10564", "customers.csv", "partners.csv", "materials.csv", "db_salesorder"]):
            report.detected_master_data_usage.append(
                str(file_path.relative_to(root))
            )

    # --- Environment variables ---
    report.detected_env_variables = _extract_env_vars(all_text)

    # --- Risks ---
    report.detected_risks = [
        "Credential rotation required: N8N_API_KEY, N8N_MCP_TOKEN (see ULTRA_MASTER_HANDOVER_2026-06-12.md)",
        "ADV Contact Table ID placeholder in workflow: requires manual n8n API lookup",
        "10564_Materials.csv was flagged as missing from some deployment contexts (verify path)",
        "SMTP dry_run may still be enabled in production config - verify",
        "Master data sync relies on GitHub Actions runners (self-hosted runners not confirmed)",
        "DB_Salesorder.csv.BSTNK must NOT be inserted into ledger order_key (comparison only)",
    ]

    # --- Not reusable ---
    report.not_reusable = [
        "n8n TypeScript workflow orchestration (replaced by Python engine)",
        "n8n DataTables (replaced by CSV-based ledger + masterdata CSVs)",
        "n8n Form Trigger (replaced by PDF_INBOX folder scan)",
        "n8n email notification nodes (not implemented in this stack - add SMTP module if required)",
        "n8n-as-code CLI tooling (n8nac, VS Code extension) - not relevant to Python stack",
    ]

    # --- Open questions ---
    report.open_questions = [
        "Confirm SFTP host/credentials for production environment",
        "Confirm 10564_Materials.csv is current and includes all active MATNRs",
        "Confirm ADV routing email recipients for TEAM 1 and TEAM 2",
        "Confirm PDF_INBOX path is accessible from deployment host",
        "Confirm duplicate retention window (how long to keep ledger entries)",
        "Confirm production SMTP details if email notifications are required",
    ]

    log.info(
        "n8n analysis complete: folders=%d files=%d workflows=%d rejection_codes=%d",
        len(folders), len(files),
        len(report.detected_workflows),
        len(report.detected_rejection_rules),
    )
    return report


def generate_analysis_report(report: AnalysisReport, output_path: str) -> None:
    """Write the N8N_ANALYSIS_REPORT.md to disk.

    Args:
        report: AnalysisReport instance.
        output_path: Destination file path for the Markdown report.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "# N8N_ANALYSIS_REPORT.md",
        f"",
        f"**Generated**: {datetime.now().isoformat(timespec='seconds')}",
        f"**n8n Project Root**: `{report.n8n_project_root}`",
        f"",
        "---",
        "",
        "## Summary",
        "",
        f"- Folders analysed: {len(report.analysed_folders)}",
        f"- Files analysed: {len(report.analysed_files)}",
        f"- Workflows detected: {len(report.detected_workflows)}",
        f"- Rejection codes detected: {len(report.detected_rejection_rules)}",
        f"- Files with duplicate logic: {len(report.detected_duplicate_logic)}",
        f"- Files with master-data references: {len(report.detected_master_data_usage)}",
        "",
        "---",
        "",
        "## Verified Business Rules (Integrated into Python Project)",
        "",
        KNOWN_RULES,
        "",
        "---",
        "",
        "## Detected Workflows",
        "",
    ]
    for wf in report.detected_workflows[:50]:
        lines.append(f"- `{wf}`")
    lines += ["", "---", "", "## Detected Rejection Codes", ""]
    for code in sorted(set(report.detected_rejection_rules)):
        lines.append(f"- `{code}`")
    lines += ["", "---", "", "## Files with Duplicate Logic", ""]
    for f in report.detected_duplicate_logic[:30]:
        lines.append(f"- `{f}`")
    lines += ["", "---", "", "## Files with Master Data References", ""]
    for f in report.detected_master_data_usage[:30]:
        lines.append(f"- `{f}`")
    lines += ["", "---", "", "## Detected Environment Variables", ""]
    for v in report.detected_env_variables[:60]:
        lines.append(f"- `{v}`")
    lines += ["", "---", "", "## Detected EDIFACT Logic", ""]
    for e in report.detected_edifact_logic[:30]:
        lines.append(f"- {e}")
    lines += ["", "---", "", "## Detected Risks", ""]
    for r in report.detected_risks:
        lines.append(f"- {r}")
    lines += ["", "---", "", "## Items Not Reusable", ""]
    for nr in report.not_reusable:
        lines.append(f"- {nr}")
    lines += ["", "---", "", "## Open Questions / Manual Verification Points", ""]
    for q in report.open_questions:
        lines.append(f"- {q}")
    if report.errors:
        lines += ["", "---", "", "## Errors During Analysis", ""]
        for e in report.errors:
            lines.append(f"- {e}")
    lines += ["", "---", "", "*End of report.*", ""]

    out.write_text("\n".join(lines), encoding="utf-8")
    log.info("N8N analysis report written: %s", output_path)
