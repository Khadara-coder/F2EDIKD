"""Databricks Delta table DDL and management for the EDIFACT Generator.

Catalog/schema from env vars:
  EDIFACT_CATALOG  (default: hive_metastore)
  EDIFACT_SCHEMA   (default: edifact_generator)
  DATABRICKS_WAREHOUSE_ID  -- required for statement execution

Falls back gracefully to in-memory/SQLite if the warehouse is not configured.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Optional

log = logging.getLogger("edifact.datatables")


def _catalog() -> str:
    return os.environ.get("EDIFACT_CATALOG", "hive_metastore")


def _schema() -> str:
    return os.environ.get("EDIFACT_SCHEMA", "edifact_generator")


def _warehouse() -> str:
    return os.environ.get("DATABRICKS_WAREHOUSE_ID", "")


# ── DDL definitions ────────────────────────────────────────────────────────────

_TABLES: dict[str, str] = {
    "customers": f"""
        CREATE TABLE IF NOT EXISTS `{_catalog()}`.`{_schema()}`.customers (
          sap_code       STRING,
          customer_vat   STRING,
          name           STRING,
          address_line_1 STRING,
          postal_code    STRING,
          city           STRING,
          country_code   STRING,
          source_file    STRING,
          source_hash    STRING,
          loaded_at      TIMESTAMP,
          active         BOOLEAN
        ) USING DELTA
    """,
    "partners": f"""
        CREATE TABLE IF NOT EXISTS `{_catalog()}`.`{_schema()}`.partners (
          partner_code       STRING,
          customer_sap_code  STRING,
          customer_vat       STRING,
          partner_role       STRING,
          name               STRING,
          address_line_1     STRING,
          postal_code        STRING,
          city               STRING,
          country_code       STRING,
          adv_team1_email    STRING,
          adv_team2_email    STRING,
          email              STRING,
          source_file        STRING,
          source_hash        STRING,
          loaded_at          TIMESTAMP,
          active             BOOLEAN
        ) USING DELTA
    """,
    "materials": f"""
        CREATE TABLE IF NOT EXISTS `{_catalog()}`.`{_schema()}`.materials (
          article_code          STRING,
          description           STRING,
          customer_article_code STRING,
          customer_vat          STRING,
          unit                  STRING,
          active                BOOLEAN,
          source_file           STRING,
          source_hash           STRING,
          loaded_at             TIMESTAMP
        ) USING DELTA
    """,
    "article_aliases": f"""
        CREATE TABLE IF NOT EXISTS `{_catalog()}`.`{_schema()}`.article_aliases (
          customer_vat          STRING,
          customer_article_code STRING,
          bosch_article_code    STRING,
          learned_from_order_key STRING,
          learned_by            STRING,
          learned_at            TIMESTAMP,
          active                BOOLEAN
        ) USING DELTA
    """,
    "order_ledger": f"""
        CREATE TABLE IF NOT EXISTS `{_catalog()}`.`{_schema()}`.order_ledger (
          order_key           STRING,
          source_filename     STRING,
          tst_filename        STRING,
          first_seen          TIMESTAMP,
          correlation_id      STRING,
          pdf_hash            STRING,
          sequence_number     STRING,
          status              STRING,
          confidence_score    DOUBLE,
          processed_at        TIMESTAMP,
          submitter_email     STRING,
          error_message       STRING,
          ai_latency_ms       BIGINT,
          total_latency_ms    BIGINT,
          replayed_from       STRING,
          rejection_code      STRING,
          rejection_message   STRING,
          business_status     STRING,
          severity            STRING,
          selected_soldto     STRING,
          selected_shipto     STRING,
          buyer_sap           STRING,
          dp_sap              STRING,
          created_at          TIMESTAMP
        ) USING DELTA
    """,
    "job_history": f"""
        CREATE TABLE IF NOT EXISTS `{_catalog()}`.`{_schema()}`.job_history (
          job_id           STRING,
          correlation_id   STRING,
          filename         STRING,
          pdf_hash         STRING,
          status           STRING,
          business_status  STRING,
          po_number        STRING,
          order_key        STRING,
          sold_to          STRING,
          ship_to          STRING,
          tst_filename     STRING,
          created_at       TIMESTAMP,
          completed_at     TIMESTAMP,
          rejection_code   STRING,
          rejection_reason STRING,
          error_detail     STRING,
          ai_latency_ms    BIGINT,
          total_latency_ms BIGINT
        ) USING DELTA
    """,
    "rejection_events": f"""
        CREATE TABLE IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`.rejection_events (
          event_id               STRING,
          correlation_id         STRING,
          order_key              STRING,
          filename               STRING,
          pdf_hash               STRING,
          rejection_code         STRING,
          rejection_message      STRING,
          severity               STRING,
          business_status        STRING,
          failed_node            STRING,
          retry_allowed          BOOLEAN,
          manual_review_required BOOLEAN,
          selected_soldto        STRING,
          selected_shipto        STRING,
          buyer_sap              STRING,
          dp_sap                 STRING,
          raw_context_json       STRING,
          created_at             TIMESTAMP,
          email_sent             BOOLEAN,
          email_sent_at          TIMESTAMP
        ) USING DELTA
    """,
    "masterdata_load_audit": f"""
        CREATE TABLE IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`.masterdata_load_audit (
          load_id         STRING,
          dataset         STRING,
          source_file     STRING,
          source_path     STRING,
          source_hash     STRING,
          rows_read       BIGINT,
          rows_loaded     BIGINT,
          rows_rejected   BIGINT,
          status          STRING,
          error_message   STRING,
          loaded_at       TIMESTAMP
        ) USING DELTA
    """,
}


@dataclass
class TableStatus:
    name: str
    success: bool
    message: str


# ── Statement Execution helper ─────────────────────────────────────────────────

def _execute_statement(sql: str) -> dict:
    """Run *sql* via Databricks StatementExecutionAPI.

    Returns a dict with keys: success, rows, columns, error.
    """
    try:
        from databricks.sdk import WorkspaceClient  # lazy
        from databricks.sdk.service.sql import StatementState

        wc  = WorkspaceClient()
        wid = WAREHOUSE
        if not wid:
            return {"success": False, "rows": [], "columns": [], "error": "DATABRICKS_WAREHOUSE_ID not set"}

        stmt = wc.statement_execution.execute_statement(
            warehouse_id=wid,
            statement=sql,
            wait_timeout="50s",
        )
        if stmt.status and stmt.status.state in (
            StatementState.SUCCEEDED, StatementState.RUNNING
        ):
            cols = []
            rows: list[list] = []
            if stmt.manifest and stmt.manifest.schema:
                cols = [c.name for c in stmt.manifest.schema.columns]
            if stmt.result and stmt.result.data_array:
                rows = [list(r) for r in stmt.result.data_array]
            return {"success": True, "rows": rows, "columns": cols, "error": None}
        err = stmt.status.error.message if (stmt.status and stmt.status.error) else "Unknown error"
        return {"success": False, "rows": [], "columns": [], "error": err}

    except Exception as exc:
        return {"success": False, "rows": [], "columns": [], "error": str(exc)}


# ── Public API ─────────────────────────────────────────────────────────────────

def create_schema_if_missing() -> TableStatus:
    """CREATE SCHEMA IF NOT EXISTS for the configured catalog/schema."""
    sql = f"CREATE SCHEMA IF NOT EXISTS `{CATALOG}`.`{SCHEMA}`"
    res = _execute_statement(sql)
    return TableStatus(
        name=f"{CATALOG}.{SCHEMA}",
        success=res["success"],
        message=res["error"] or "Schema ready",
    )


def create_all_tables() -> list[TableStatus]:
    """Create all 8 Delta tables if they do not already exist.

    Returns one TableStatus per table.
    """
    results: list[TableStatus] = []

    if not WAREHOUSE:
        log.warning("DATABRICKS_WAREHOUSE_ID not set -- skipping Delta table creation")
        for name in _TABLES:
            results.append(TableStatus(name=name, success=False,
                                        message="DATABRICKS_WAREHOUSE_ID not configured"))
        return results

    # Ensure schema exists first
    schema_status = create_schema_if_missing()
    if not schema_status.success:
        for name in _TABLES:
            results.append(TableStatus(name=name, success=False,
                                        message=f"Schema creation failed: {schema_status.message}"))
        return results

    for name, ddl in _TABLES.items():
        res = _execute_statement(ddl.strip())
        results.append(TableStatus(
            name=f"{CATALOG}.{SCHEMA}.{name}",
            success=res["success"],
            message=res["error"] or "OK",
        ))
        log.info("Table %s.%s.%s: %s", CATALOG, SCHEMA, name,
                 "created/exists" if res["success"] else res["error"])
    return results


def insert_job_history(row: dict) -> bool:
    """INSERT one row into job_history Delta table.

    *row* keys must match the table schema.  Unknown keys are silently dropped.
    Falls back gracefully if warehouse unavailable.
    """
    if not WAREHOUSE:
        return False

    cols = ["job_id", "correlation_id", "filename", "pdf_hash", "status",
            "business_status", "po_number", "order_key", "sold_to", "ship_to",
            "tst_filename", "created_at", "completed_at", "rejection_code",
            "rejection_reason", "error_detail", "ai_latency_ms", "total_latency_ms"]

    def _q(v: object) -> str:
        if v is None:
            return "NULL"
        return "'" + str(v).replace("'", "''") + "'"

    values = ", ".join(_q(row.get(c)) for c in cols)
    sql = (
        f"INSERT INTO `{CATALOG}`.`{SCHEMA}`.job_history "
        f"({', '.join(cols)}) VALUES ({values})"
    )
    res = _execute_statement(sql)
    return res["success"]


def query_job_history(limit: int = 100) -> list[list]:
    """Return the last *limit* rows from job_history Delta table.

    Falls back to empty list if warehouse unavailable.
    """
    if not WAREHOUSE:
        return []
    sql = (
        f"SELECT job_id, filename, status, po_number, sold_to, ship_to, "
        f"created_at, rejection_reason "
        f"FROM `{CATALOG}`.`{SCHEMA}`.job_history "
        f"ORDER BY created_at DESC "
        f"LIMIT {limit}"
    )
    res = _execute_statement(sql)
    return res.get("rows", []) if res["success"] else []
