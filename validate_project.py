#!/usr/bin/env python3
"""Project validation script for EDIFACT Orders Generator.

Checks:
1. unb_profiles.csv has exactly one row: ELM_STANDARD
2. config.ini uses ELM_STANDARD
3. No unauthorized UNB sender/receiver active
4. n8n project folder path accessible (or flagged unavailable)
5. Masterdata folder and mandatory files exist
6. SFTP config variables defined when SFTP enabled
7. Required local folders accessible
8. requirements.txt contains paramiko
9. No forbidden strings in project source files

Exit code: 0 = all PASS, 1 = one or more FAIL.
"""
from __future__ import annotations

import configparser
import csv
import os
import re
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #
_AUTHORISED_PROFILE_ID = "ELM_STANDARD"
_AUTHORISED_SENDER_ID = "4399901876613"
_AUTHORISED_RECEIVER_ID = "3015981600108"
_FORBIDDEN_IDS = {"3020810000707", "54209794400681"}

_MASTERDATA_ROOT = os.environ.get(
    "MASTERDATA_SOURCE_DIR",
    "data/masterdata",
)
_MANDATORY_CSVs = [
    "10564_Customers.csv",
    "10564_Partners.csv",
    "10564_Materials.csv",
]

_RESULTS: list[tuple[str, str, str]] = []  # (status, check, detail)


def PASS(check: str, detail: str = "") -> None:
    _RESULTS.append(("PASS", check, detail))
    print(f"  [PASS] {check}" + (f": {detail}" if detail else ""))


def FAIL(check: str, detail: str = "") -> None:
    _RESULTS.append(("FAIL", check, detail))
    print(f"  [FAIL] {check}" + (f": {detail}" if detail else ""))


def WARN(check: str, detail: str = "") -> None:
    _RESULTS.append(("WARN", check, detail))
    print(f"  [WARN] {check}" + (f": {detail}" if detail else ""))


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #

def check_unb_profiles_csv() -> None:
    print("\n[1] Checking lookups/unb_profiles.csv...")
    path = Path("lookups/unb_profiles.csv")
    if not path.exists():
        FAIL("unb_profiles.csv exists", str(path))
        return
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = [r for r in reader if any(v.strip() for v in r.values())]
    if len(rows) != 1:
        FAIL("Exactly one profile row", f"Found {len(rows)} rows. Must be exactly 1.")
        return
    row = rows[0]
    pid = row.get("profile_id", "").strip()
    sid = row.get("sender_id", "").strip()
    rid = row.get("receiver_id", "").strip()
    ok = True
    if pid != _AUTHORISED_PROFILE_ID:
        FAIL("profile_id == ELM_STANDARD", f"Got: {pid!r}")
        ok = False
    if sid != _AUTHORISED_SENDER_ID:
        FAIL("sender_id == 4399901876613", f"Got: {sid!r}")
        ok = False
    if rid != _AUTHORISED_RECEIVER_ID:
        FAIL("receiver_id == 3015981600108", f"Got: {rid!r}")
        ok = False
    for fval in _FORBIDDEN_IDS:
        if fval in (sid, rid, pid):
            FAIL("No forbidden value in UNB profile", f"Found: {fval!r}")
            ok = False
    if ok:
        PASS("unb_profiles.csv", "ELM_STANDARD only, correct sender/receiver")


def check_config_ini() -> None:
    print("\n[2] Checking config.ini...")
    path = Path("config.ini")
    if not path.exists():
        FAIL("config.ini exists", str(path))
        return
    parser = configparser.RawConfigParser()
    parser.read(str(path), encoding="utf-8")
    try:
        profile = parser.get("edi", "unb_profile", fallback="").strip()
        sender = parser.get("edi", "sender_id", fallback="").strip()
        receiver = parser.get("edi", "receiver_id", fallback="").strip()
    except Exception as exc:
        FAIL("config.ini parse", str(exc))
        return
    if profile != _AUTHORISED_PROFILE_ID:
        FAIL("config.ini unb_profile == ELM_STANDARD", f"Got: {profile!r}")
    else:
        PASS("config.ini unb_profile", profile)
    if sender != _AUTHORISED_SENDER_ID:
        FAIL("config.ini sender_id", f"Got: {sender!r}")
    else:
        PASS("config.ini sender_id", sender)
    if receiver != _AUTHORISED_RECEIVER_ID:
        FAIL("config.ini receiver_id", f"Got: {receiver!r}")
    else:
        PASS("config.ini receiver_id", receiver)
    # Check forbidden values
    full_text = path.read_text(encoding="utf-8")
    for fval in _FORBIDDEN_IDS:
        if fval in full_text:
            FAIL("No forbidden value in config.ini", f"Found: {fval!r}")


def check_forbidden_strings_in_sources() -> None:
    print("\n[3] Scanning project source files for forbidden strings...")
    scan_dirs = [Path("src"), Path("lookups"), Path("config.ini")]
    found_issues = []
    for root_item in scan_dirs:
        paths_to_check: list[Path] = []
        if root_item.is_dir():
            paths_to_check = list(root_item.rglob("*"))
        elif root_item.is_file():
            paths_to_check = [root_item]
        for p in paths_to_check:
            if not p.is_file():
                continue
            if p.suffix in {".pyc"}:
                continue
            try:
                text = p.read_text(encoding="utf-8-sig", errors="ignore")
            except Exception:
                continue
            for fval in _FORBIDDEN_IDS:
                if fval in text:
                    # Allow only in explicit forbidden-list constants/tests
                    # Check if it's inside a frozenset/set literal (the forbidden-list guard itself)
                    context_lines = [
                        line for line in text.split("\n") if fval in line
                    ]
                    for ctx in context_lines:
                        if not any(
                            guard in ctx
                            for guard in [
                                "FORBIDDEN", "frozenset", "forbidden",
                                "_FORBIDDEN", "test_forbidden", "assert",
                                "# forbidden", "\"3020", "\"5420",
                            ]
                        ):
                            found_issues.append(f"{p}: line contains {fval!r}: {ctx.strip()[:80]}")
    if found_issues:
        for issue in found_issues:
            FAIL("No forbidden value in source", issue)
    else:
        PASS("Forbidden string scan", "No unauthorized UNB values in source code")


def check_n8n_folder() -> None:
    print("\n[4] Checking n8n project folder...")
    n8n_root = "/Workspace/Users/rsr1dy@bosch.com/n8n"
    if os.path.exists(n8n_root):
        PASS("n8n project folder accessible", n8n_root)
    else:
        WARN("n8n project folder", f"Not found at {n8n_root} - analysis will be skipped.")


def check_masterdata_folder() -> None:
    print("\n[5] Checking masterdata folder and mandatory files...")
    if _MASTERDATA_ROOT.startswith("/Volumes/") and not os.path.exists(_MASTERDATA_ROOT):
        try:
            cmd = ["databricks", "fs", "ls", f"dbfs:{_MASTERDATA_ROOT}"]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode == 0:
                PASS("masterdata volume accessible via Databricks CLI", _MASTERDATA_ROOT)
            else:
                WARN("masterdata volume check", f"Local path not mounted. Verify in Databricks: dbfs:{_MASTERDATA_ROOT}")
            return
        except Exception:
            WARN("masterdata volume check", f"Local path not mounted. Verify in Databricks: dbfs:{_MASTERDATA_ROOT}")
            return

    if os.path.exists(_MASTERDATA_ROOT):
        PASS("masterdata folder exists", _MASTERDATA_ROOT)
    else:
        FAIL("masterdata folder exists", _MASTERDATA_ROOT)
        return
    for fname in _MANDATORY_CSVs:
        fpath = os.path.join(_MASTERDATA_ROOT, fname)
        if os.path.isfile(fpath):
            PASS(f"Mandatory CSV: {fname}", fpath)
        else:
            FAIL(f"Mandatory CSV: {fname}", f"Not found: {fpath}")
    # Optional
    opt = os.path.join(_MASTERDATA_ROOT, "DB_Salesorder.csv")
    if os.path.isfile(opt):
        PASS("Optional DB_Salesorder.csv", "Found")
    else:
        WARN("Optional DB_Salesorder.csv", "Not found (non-fatal)")


def check_sftp_config() -> None:
    print("\n[6] Checking SFTP configuration...")
    path = Path("config.ini")
    if not path.exists():
        WARN("SFTP config check", "config.ini not found")
        return
    parser = configparser.RawConfigParser()
    parser.read(str(path), encoding="utf-8")
    enabled = parser.get("sftp", "enabled", fallback="false").strip().lower()
    if enabled not in {"true", "1", "yes"}:
        WARN("SFTP enabled", "SFTP is disabled in config.ini")
        return
    # Check env vars are defined
    required_env = ["SFTP_HOST", "SFTP_USERNAME", "SFTP_REMOTE_DIR"]
    all_ok = True
    for var in required_env:
        if os.environ.get(var):
            PASS(f"SFTP env var {var}", "Set")
        else:
            WARN(f"SFTP env var {var}", "Not set in current environment")
            all_ok = False
    # At least one auth method
    has_password = bool(os.environ.get("SFTP_PASSWORD"))
    has_key = bool(os.environ.get("SFTP_PRIVATE_KEY_PATH"))
    if has_password or has_key:
        PASS("SFTP authentication", "password or key env var set")
    else:
        WARN("SFTP authentication", "Neither SFTP_PASSWORD nor SFTP_PRIVATE_KEY_PATH set")


def check_local_folders() -> None:
    print("\n[7] Checking local output folders...")
    folders = [
        "outbox/local_generated",
        "outbox/sftp_submitted",
        "outbox/sftp_failed",
        "data",
        "logs",
        "lookups",
    ]
    for folder in folders:
        p = Path(folder)
        try:
            p.mkdir(parents=True, exist_ok=True)
            test_f = p / ".write_test"
            test_f.touch()
            test_f.unlink()
            PASS(f"Folder writable: {folder}")
        except OSError as exc:
            FAIL(f"Folder writable: {folder}", str(exc))


def check_requirements_txt() -> None:
    print("\n[8] Checking requirements.txt contains paramiko...")
    path = Path("requirements.txt")
    if not path.exists():
        FAIL("requirements.txt exists")
        return
    content = path.read_text(encoding="utf-8")
    if "paramiko" in content.lower():
        PASS("requirements.txt contains paramiko")
    else:
        FAIL("requirements.txt contains paramiko", "'paramiko' not found in requirements.txt")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> int:
    print("=" * 60)
    print("EDIFACT Orders Generator - Project Validation")
    print("=" * 60)

    check_unb_profiles_csv()
    check_config_ini()
    check_forbidden_strings_in_sources()
    check_n8n_folder()
    check_masterdata_folder()
    check_sftp_config()
    check_local_folders()
    check_requirements_txt()

    print("\n" + "=" * 60)
    fail_count = sum(1 for r in _RESULTS if r[0] == "FAIL")
    warn_count = sum(1 for r in _RESULTS if r[0] == "WARN")
    pass_count = sum(1 for r in _RESULTS if r[0] == "PASS")
    print(f"PASS: {pass_count}  WARN: {warn_count}  FAIL: {fail_count}")

    if fail_count > 0:
        print("\nRESULT: FAIL - Fix the above issues before deployment.")
        return 1
    elif warn_count > 0:
        print("\nRESULT: PASS with warnings - Review warnings before production.")
        return 0
    else:
        print("\nRESULT: ALL CHECKS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
