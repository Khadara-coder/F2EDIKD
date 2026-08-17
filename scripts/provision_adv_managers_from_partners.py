#!/usr/bin/env python3
"""Provision ADV manager accounts from Partners masterdata and backfill order assignees.

Reads ``10564_Partners.csv`` (columns Fonction-Partenaire, Gestionaire-ADV, Email-I.D, User-I.D),
creates missing ``adv`` users (sap_id = Fonction-Partenaire), then sets ``assigned_to`` on orders
whose SOLDTO maps to a gestionnaire.

Idempotent: skips existing usernames; only fills empty assigned_to.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _partners_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    for candidate in (
        ROOT / "data" / "masterdata" / "10564_Partners.csv",
        Path("/app/data/masterdata/10564_Partners.csv"),
    ):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("10564_Partners.csv introuvable")


def _pick_column(columns: list[str], *candidates: str) -> str | None:
    def _norm(value: str) -> str:
        return (
            value.strip()
            .lower()
            .replace(" ", "")
            .replace("_", "")
            .replace("-", "")
            .replace(".", "")
        )

    normalized = {c: _norm(c) for c in columns}
    for candidate in candidates:
        target = _norm(candidate)
        for original, norm in normalized.items():
            if norm == target:
                return original
    return None


def _load_gestionnaires(partners_path: Path) -> list[dict]:
    import pandas as pd

    df = pd.read_csv(partners_path, sep=";", dtype=str)
    col_fp = _pick_column(list(df.columns), "Fonction-Partenaire", "Fonction Partenaire")
    col_name = _pick_column(list(df.columns), "Gestionaire-ADV", "Gestionnaire-ADV", "Gestionnaire ADV")
    col_email = _pick_column(list(df.columns), "Email-I.D", "Email I.D", "Email")
    col_user = _pick_column(list(df.columns), "User-I.D", "User I.D", "User ID")
    if not all([col_fp, col_name, col_email, col_user]):
        raise ValueError(f"Colonnes gestionnaire manquantes dans {partners_path}: {list(df.columns)}")

    subset = df[[col_fp, col_name, col_email, col_user]].copy()
    subset[col_user] = subset[col_user].astype(str).str.strip()
    subset[col_fp] = subset[col_fp].astype(str).str.strip()
    subset = subset[(subset[col_user] != "") & (subset[col_user].str.lower() != "nan")]
    subset = subset.drop_duplicates(subset=[col_user], keep="first")

    rows: list[dict] = []
    for _, row in subset.iterrows():
        username = str(row[col_user]).strip().lower()
        sap_id = str(row[col_fp]).strip()
        if not username or not sap_id:
            continue
        rows.append(
            {
                "username": username,
                "displayName": str(row[col_name] or username).strip(),
                "email": str(row[col_email] or "").strip(),
                "sapId": sap_id,
            }
        )
    return rows


def _load_soldto_to_sap_id(partners_path: Path) -> dict[str, str]:
    import pandas as pd

    df = pd.read_csv(partners_path, sep=";", dtype=str)
    col_fp = _pick_column(list(df.columns), "Fonction-Partenaire", "Fonction Partenaire")
    col_soldto = _pick_column(list(df.columns), "SOLDTO")
    if not col_fp or not col_soldto:
        return {}
    mapping: dict[str, str] = {}
    for _, row in df.dropna(subset=[col_soldto, col_fp]).iterrows():
        soldto = str(row[col_soldto]).strip()
        sap_id = str(row[col_fp]).strip()
        if soldto and sap_id:
            mapping[soldto] = sap_id
    return mapping


def provision_users(store, gestionnaires: list[dict], *, default_password: str, dry_run: bool) -> dict:
    existing = {u["username"].lower(): u for u in store.list_users()}
    created = 0
    updated = 0
    skipped = 0

    for g in gestionnaires:
        username = g["username"]
        current = existing.get(username)
        if current:
            needs_update = (
                (g["sapId"] and str(current.get("sapId") or "") != g["sapId"])
                or (g["email"] and str(current.get("email") or "").lower() != g["email"].lower())
                or (g["displayName"] and str(current.get("displayName") or "") != g["displayName"])
            )
            if needs_update:
                print(f"  ~ update {username} sap={g['sapId']} email={g['email']}")
                if not dry_run:
                    store.update_user(
                        current["userId"],
                        display_name=g["displayName"],
                        email=g["email"],
                        sap_id=g["sapId"],
                        role="adv",
                    )
                updated += 1
            else:
                skipped += 1
            continue

        print(f"  + create {username} ({g['displayName']}) sap={g['sapId']}")
        if not dry_run:
            store.create_user(
                username=username,
                display_name=g["displayName"],
                password=default_password,
                email=g["email"],
                sap_id=g["sapId"],
                role="adv",
            )
        created += 1

    return {"created": created, "updated": updated, "skipped": skipped}


def backfill_assignments(store, soldto_to_sap: dict[str, str], *, dry_run: bool) -> dict:
    from src.file2edi.store import _now

    users = store.list_users()
    sap_to_username = {
        str(u.get("sapId") or "").strip(): u["username"]
        for u in users
        if str(u.get("sapId") or "").strip()
    }

    conn = store._conn()
    rows = conn.execute(
        """SELECT order_id, soldto, assigned_to, status
           FROM file2edi_orders
           ORDER BY created_at DESC"""
    ).fetchall()
    assigned = 0
    missing_mapping = 0
    already = 0

    for row in rows:
        order_id = row["order_id"]
        if str(row["assigned_to"] or "").strip():
            already += 1
            continue
        soldto = str(row["soldto"] or "").strip()
        if not soldto:
            missing_mapping += 1
            continue
        sap_id = soldto_to_sap.get(soldto)
        if not sap_id:
            missing_mapping += 1
            continue
        username = sap_to_username.get(sap_id)
        if not username:
            missing_mapping += 1
            continue
        print(f"  -> order {order_id[:12]}… soldto={soldto} assigned_to={username}")
        if not dry_run:
            conn.execute(
                "UPDATE file2edi_orders SET assigned_to=?, updated_at=? WHERE order_id=?",
                [username, _now(), order_id],
            )
        assigned += 1

    if not dry_run:
        conn.commit()
    conn.close()
    return {"assigned": assigned, "already_assigned": already, "unmapped": missing_mapping}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partners", help="Path to 10564_Partners.csv")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--password",
        default=os.environ.get("APP_PROFILE_LOGIN_PASSWORD", "adv123"),
        help="Default password for newly created ADV accounts",
    )
    args = parser.parse_args()

    partners_path = _partners_path(args.partners)
    gestionnaires = _load_gestionnaires(partners_path)
    soldto_to_sap = _load_soldto_to_sap_id(partners_path)

    print(f"Partners: {partners_path}")
    print(f"Gestionnaires uniques: {len(gestionnaires)}")
    print(f"Mappings SOLDTO: {len(soldto_to_sap)}")

    from src.file2edi.store import get_store

    store = get_store()

    print("\n1) Comptes gestionnaires")
    user_stats = provision_users(store, gestionnaires, default_password=args.password, dry_run=args.dry_run)

    print("\n2) Backfill assigned_to")
    assign_stats = backfill_assignments(store, soldto_to_sap, dry_run=args.dry_run)

    print("\nRésumé")
    print(f"  users created={user_stats['created']} updated={user_stats['updated']} skipped={user_stats['skipped']}")
    print(
        f"  orders assigned={assign_stats['assigned']} "
        f"already={assign_stats['already_assigned']} unmapped={assign_stats['unmapped']}"
    )
    if args.dry_run:
        print("  (dry-run — aucune écriture)")
    elif user_stats["created"]:
        print(f"  Mot de passe initial des nouveaux comptes: {args.password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
