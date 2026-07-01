/**
 * Databricks SQL Warehouse connector.
 * All SQL queries run server-side only — never from the browser.
 *
 * Set MOCK_MODE=true for local development without Databricks credentials.
 */
import { DBSQLClient } from "@databricks/sql";

export interface DatabricksConfig {
  serverHostname: string;
  httpPath: string;
  token: string;
  catalog: string;
  schema: string;
}

export function getDatabricksConfig(): DatabricksConfig {
  return {
    serverHostname: process.env.DATABRICKS_SERVER_HOSTNAME ?? "",
    httpPath: process.env.DATABRICKS_HTTP_PATH ?? "",
    token: process.env.DATABRICKS_TOKEN ?? "",
    catalog: process.env.DATABRICKS_CATALOG ?? "hive_metastore",
    schema: process.env.DATABRICKS_SCHEMA ?? "file2edi",
  };
}

export function isMockMode(): boolean {
  return (
    process.env.MOCK_MODE === "true" ||
    !process.env.DATABRICKS_SERVER_HOSTNAME ||
    !process.env.DATABRICKS_TOKEN
  );
}

export async function executeQuery<T extends Record<string, unknown>>(
  sql: string,
  params: unknown[] = [],
): Promise<T[]> {
  if (isMockMode()) {
    throw new Error("Databricks not configured — use mock store in MOCK_MODE");
  }

  const cfg = getDatabricksConfig();
  const client = new DBSQLClient();
  const connection = await client.connect({
    host: cfg.serverHostname,
    path: cfg.httpPath,
    token: cfg.token,
  });

  try {
    const session = await connection.openSession();
    const queryOperation = await session.executeStatement(sql, {
      runAsync: false,
      maxRows: 10_000,
    });
    const result = await queryOperation.fetchAll();
    await queryOperation.close();
    await session.close();
    return result as T[];
  } finally {
    await connection.close();
  }
}

export function qualifiedTable(tableName: string): string {
  const { catalog, schema } = getDatabricksConfig();
  return `${catalog}.${schema}.${tableName}`;
}

/** DDL reference for Unity Catalog / Delta Tables */
export const TABLE_DEFINITIONS = {
  file2edi_pdf_uploads: `
    CREATE TABLE IF NOT EXISTS file2edi_pdf_uploads (
      upload_id STRING,
      file_name STRING,
      file_size BIGINT,
      file_path STRING,
      uploaded_at TIMESTAMP,
      uploaded_by STRING,
      status STRING
    ) USING DELTA
  `,
  file2edi_orders: `
    CREATE TABLE IF NOT EXISTS file2edi_orders (
      order_id STRING,
      upload_id STRING,
      client_name STRING,
      customer_order_number STRING,
      document_reference STRING,
      order_date DATE,
      requested_delivery_date DATE,
      currency STRING,
      incoterm STRING,
      delivery_mode STRING,
      total_amount DOUBLE,
      global_confidence DOUBLE,
      status STRING,
      review_required BOOLEAN,
      created_at TIMESTAMP,
      updated_at TIMESTAMP
    ) USING DELTA
  `,
  file2edi_order_lines: `
    CREATE TABLE IF NOT EXISTS file2edi_order_lines (
      line_id STRING,
      order_id STRING,
      line_number INT,
      customer_reference STRING,
      bosch_article STRING,
      designation STRING,
      quantity DOUBLE,
      unit STRING,
      unit_price DOUBLE,
      amount DOUBLE,
      confidence DOUBLE,
      status STRING,
      comment STRING
    ) USING DELTA
  `,
};
