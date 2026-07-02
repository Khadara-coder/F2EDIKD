-- File2EDI order-centric tables (SQLite local + Delta mirror via scripts/create_delta_tables.sql)
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS file2edi_pdf_uploads (
  upload_id     TEXT PRIMARY KEY,
  file_name     TEXT NOT NULL,
  file_size     INTEGER NOT NULL,
  file_path     TEXT NOT NULL,
  uploaded_at   TEXT NOT NULL,
  uploaded_by   TEXT DEFAULT 'operator',
  status        TEXT DEFAULT 'RECEIVED'
);

CREATE TABLE IF NOT EXISTS file2edi_orders (
  order_id                  TEXT PRIMARY KEY,
  upload_id                 TEXT,
  file_name                 TEXT,
  client_name               TEXT,
  customer_order_number     TEXT,
  document_reference        TEXT,
  order_date                TEXT,
  requested_delivery_date   TEXT,
  currency                  TEXT DEFAULT 'EUR',
  incoterm                  TEXT DEFAULT 'DAP',
  delivery_mode             TEXT,
  message_type              TEXT DEFAULT 'ORDERS',
  vendor                    TEXT,
  total_amount              REAL DEFAULT 0,
  global_confidence         REAL DEFAULT 0,
  status                    TEXT DEFAULT 'Revue requise',
  review_required           INTEGER DEFAULT 1,
  line_count                INTEGER DEFAULT 0,
  pdf_hash                  TEXT,
  pdf_path                  TEXT,
  edifact_content           TEXT,
  edifact_filename          TEXT,
  extraction_json           TEXT,
  corrections_json          TEXT,
  created_at                TEXT NOT NULL,
  updated_at                TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_f2e_orders_status ON file2edi_orders(status);
CREATE INDEX IF NOT EXISTS idx_f2e_orders_upload ON file2edi_orders(upload_id);

CREATE TABLE IF NOT EXISTS file2edi_order_partners (
  partner_id        TEXT PRIMARY KEY,
  order_id          TEXT NOT NULL,
  partner_function  TEXT NOT NULL,
  partner_code      TEXT,
  partner_name      TEXT,
  address_line_1    TEXT,
  address_line_2    TEXT,
  postal_code       TEXT,
  city              TEXT,
  country           TEXT DEFAULT 'FR',
  confidence        REAL DEFAULT 0,
  manually_edited   INTEGER DEFAULT 0,
  edited_fields_json TEXT,
  previous_value    TEXT,
  FOREIGN KEY(order_id) REFERENCES file2edi_orders(order_id)
);

CREATE TABLE IF NOT EXISTS file2edi_order_lines (
  line_id             TEXT PRIMARY KEY,
  order_id            TEXT NOT NULL,
  line_number         INTEGER NOT NULL,
  customer_reference  TEXT,
  bosch_article       TEXT,
  designation         TEXT,
  quantity            REAL DEFAULT 0,
  unit                TEXT DEFAULT 'PCE',
  unit_price          REAL DEFAULT 0,
  amount              REAL DEFAULT 0,
  confidence          REAL DEFAULT 0,
  status              TEXT DEFAULT 'OK',
  comment             TEXT,
  manually_edited     INTEGER DEFAULT 0,
  FOREIGN KEY(order_id) REFERENCES file2edi_orders(order_id)
);

CREATE INDEX IF NOT EXISTS idx_f2e_lines_order ON file2edi_order_lines(order_id);

CREATE TABLE IF NOT EXISTS file2edi_order_anomalies (
  anomaly_id    TEXT PRIMARY KEY,
  order_id      TEXT NOT NULL,
  line_id       TEXT,
  severity      TEXT DEFAULT 'warning',
  field_name    TEXT,
  message       TEXT NOT NULL,
  status        TEXT DEFAULT 'Ouverte',
  created_at    TEXT NOT NULL,
  FOREIGN KEY(order_id) REFERENCES file2edi_orders(order_id)
);

CREATE TABLE IF NOT EXISTS file2edi_conversion_history (
  conversion_id   TEXT PRIMARY KEY,
  order_id        TEXT NOT NULL,
  file_name       TEXT,
  status          TEXT,
  confidence      REAL,
  edifact_path    TEXT,
  processed_at    TEXT NOT NULL,
  processed_by    TEXT DEFAULT 'system'
);

CREATE TABLE IF NOT EXISTS file2edi_settings (
  setting_key     TEXT PRIMARY KEY,
  setting_value   TEXT NOT NULL,
  updated_at      TEXT NOT NULL
);
