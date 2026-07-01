-- EDIFACT Standalone Orchestrator — SQLite schema
-- Used by src/database.py (API / worker mode)
-- Batch mode uses CSV ledgers in data/duplicate_ledger.csv instead

PRAGMA journal_mode = WAL;

-- --------------------------------------------------------
-- Jobs
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
  id                TEXT PRIMARY KEY,
  source_filename   TEXT NOT NULL,
  source_path       TEXT NOT NULL,
  po_number         TEXT,
  soldto            TEXT,          -- resolved Sold-to from master data
  status            TEXT NOT NULL, -- RECEIVED | PROCESSING | COMPLETED | REJECTED | DUPLICATE | FAILED | RETRY
  rejection_reason  TEXT,
  output_filename   TEXT,
  output_path       TEXT,
  error_message     TEXT,
  created_at        TEXT NOT NULL,
  updated_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status     ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_po_number  ON jobs(po_number);
CREATE INDEX IF NOT EXISTS idx_jobs_soldto     ON jobs(soldto);

-- --------------------------------------------------------
-- Job event log
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id      TEXT    NOT NULL,
  event_type  TEXT    NOT NULL,
  details     TEXT,
  created_at  TEXT    NOT NULL,
  FOREIGN KEY(job_id) REFERENCES jobs(id)
);

CREATE INDEX IF NOT EXISTS idx_job_events_job_id ON job_events(job_id);

-- --------------------------------------------------------
-- Dedupe ledger
-- 3-component key: order_number + soldto + pdf_sha256  (n8n rule)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS dedupe_ledger (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  dedupe_key     TEXT NOT NULL UNIQUE,  -- po_number:soldto:sha256
  po_number      TEXT NOT NULL,
  soldto         TEXT,
  source_hash    TEXT,
  first_seen_at  TEXT NOT NULL,
  last_seen_at   TEXT NOT NULL,
  hit_count      INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_dedupe_po_number ON dedupe_ledger(po_number);
CREATE INDEX IF NOT EXISTS idx_dedupe_soldto    ON dedupe_ledger(soldto);

-- --------------------------------------------------------
-- ADV contacts (replaces n8n Partners data table)
-- --------------------------------------------------------
CREATE TABLE IF NOT EXISTS adv_contacts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  soldto      TEXT NOT NULL,
  dept        TEXT,          -- postal[0:2] DEPT code
  email       TEXT NOT NULL,
  active      INTEGER NOT NULL DEFAULT 1,
  updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_adv_contacts_soldto ON adv_contacts(soldto);
