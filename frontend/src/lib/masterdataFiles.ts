/** Bosch masterdata filenames → UI tab / API kind hint. */
const FILENAME_KIND: Record<string, string> = {
  "10564_customers": "clients",
  "10564_partners": "shipto",
  "db_materials": "articles",
  "10564_materials": "articles",
  "db_salesorder": "salesorders",
};

const KIND_LABEL: Record<string, string> = {
  clients: "Clients",
  shipto: "Ship-to",
  articles: "Articles",
  salesorders: "Commandes SAP",
};

export function detectMasterDataKindFromFilename(filename: string): string | null {
  const base = filename.split(/[/\\]/).pop()?.trim().toLowerCase() ?? "";
  if (!base.endsWith(".csv") && !base.endsWith(".parquet")) return null;
  const stem = base.replace(/\.(csv|parquet)$/, "");
  return FILENAME_KIND[stem] ?? null;
}

export function masterDataKindLabel(kind: string | null | undefined): string {
  if (!kind) return "Inconnu";
  return KIND_LABEL[kind] ?? kind;
}

export const MASTERDATA_ACCEPT = ".csv,.parquet,application/vnd.apache.parquet,text/csv";

export const MASTERDATA_FILENAME_HINT =
  "10564_Customers, 10564_Partners, DB_Materials, DB_Salesorder (.csv ou .parquet)";
