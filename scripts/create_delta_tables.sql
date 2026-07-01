-- File2EDI — Unity Catalog / Delta Tables (run once with warehouse admin rights)
-- Replace ${CATALOG} and ${SCHEMA} before execution.

CREATE SCHEMA IF NOT EXISTS ${CATALOG}.${SCHEMA};

CREATE TABLE IF NOT EXISTS ${CATALOG}.${SCHEMA}.file2edi_pdf_uploads (
  upload_id     STRING NOT NULL,
  file_name     STRING NOT NULL,
  file_size     BIGINT,
  file_path     STRING,
  uploaded_at   TIMESTAMP,
  uploaded_by   STRING,
  status        STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS ${CATALOG}.${SCHEMA}.file2edi_orders (
  order_id                  STRING NOT NULL,
  upload_id                 STRING,
  client_name               STRING,
  customer_order_number     STRING,
  document_reference        STRING,
  order_date                DATE,
  requested_delivery_date   DATE,
  currency                  STRING,
  incoterm                  STRING,
  delivery_mode             STRING,
  total_amount              DOUBLE,
  global_confidence         DOUBLE,
  status                    STRING,
  review_required           BOOLEAN,
  created_at                TIMESTAMP,
  updated_at                TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS ${CATALOG}.${SCHEMA}.file2edi_order_partners (
  partner_id        STRING NOT NULL,
  order_id          STRING NOT NULL,
  partner_function  STRING,
  partner_code      STRING,
  partner_name      STRING,
  address_line_1    STRING,
  address_line_2    STRING,
  postal_code       STRING,
  city              STRING,
  country           STRING,
  confidence        DOUBLE
) USING DELTA;

CREATE TABLE IF NOT EXISTS ${CATALOG}.${SCHEMA}.file2edi_order_lines (
  line_id             STRING NOT NULL,
  order_id            STRING NOT NULL,
  line_number         INT,
  customer_reference  STRING,
  bosch_article       STRING,
  designation         STRING,
  quantity            DOUBLE,
  unit                STRING,
  unit_price          DOUBLE,
  amount              DOUBLE,
  confidence          DOUBLE,
  status              STRING,
  comment             STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS ${CATALOG}.${SCHEMA}.file2edi_order_anomalies (
  anomaly_id    STRING NOT NULL,
  order_id      STRING NOT NULL,
  line_id       STRING,
  severity      STRING,
  field_name    STRING,
  message       STRING,
  status        STRING,
  created_at    TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS ${CATALOG}.${SCHEMA}.file2edi_conversion_history (
  conversion_id   STRING NOT NULL,
  order_id        STRING NOT NULL,
  file_name       STRING,
  status          STRING,
  confidence      DOUBLE,
  edifact_path    STRING,
  processed_at    TIMESTAMP,
  processed_by    STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS ${CATALOG}.${SCHEMA}.file2edi_settings (
  setting_key     STRING NOT NULL,
  setting_value   STRING,
  updated_at      TIMESTAMP
) USING DELTA;

-- Existing platform tables (server.py persistence adapter)
CREATE TABLE IF NOT EXISTS ${CATALOG}.${SCHEMA}.file2edi_conversions (
  id STRING NOT NULL,
  correlation_id STRING,
  source_filename STRING,
  pdf_hash STRING,
  order_key STRING,
  status STRING,
  business_status STRING,
  delivery_status STRING,
  po_number STRING,
  order_date STRING,
  delivery_date STRING,
  soldto STRING,
  shipto STRING,
  customer_name STRING,
  confidence INT,
  line_count INT,
  missing_material_count INT,
  rejection_code STRING,
  rejection_message STRING,
  tst_filename STRING,
  edifact_content STRING,
  sftp_status STRING,
  email_status STRING,
  operator STRING,
  corrections_json STRING,
  extraction_json STRING,
  created_at STRING,
  updated_at STRING
) USING DELTA TBLPROPERTIES ('delta.autoOptimize.optimizeWrite' = 'true');

CREATE TABLE IF NOT EXISTS ${CATALOG}.${SCHEMA}.file2edi_audit_events (
  id BIGINT,
  conversion_id STRING NOT NULL,
  event_type STRING NOT NULL,
  actor STRING,
  payload STRING,
  result STRING,
  created_at STRING
) USING DELTA;
