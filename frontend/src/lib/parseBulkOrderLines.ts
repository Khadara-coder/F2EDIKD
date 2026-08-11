export interface ParsedBulkOrderLine {
  rowIndex: number;
  boschArticle: string;
  quantity: number;
  unitPrice: number;
  valid: boolean;
  error?: string;
}

export interface BulkOrderLineDraft {
  id: string;
  boschArticle: string;
  quantity: string;
  unitPrice: string;
}

const HEADER_PATTERN = /^(code|article|r[eé]f|matnr|qt[eé]|qty|quantit|p\.?u|prix|unit)/i;
const DEFAULT_EMPTY_ROWS = 5;

function detectDelimiter(line: string): string {
  if (line.includes("\t")) return "\t";
  if (line.includes(";")) return ";";
  if (line.includes(",")) return ",";
  return "\t";
}

function cleanCell(raw: string): string {
  return raw.trim().replace(/^["']|["']$/g, "");
}

export function parseNumber(raw: string): number | null {
  const normalized = raw.trim().replace(/\s/g, "").replace(",", ".");
  if (!normalized) return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

function splitRow(line: string, delimiter: string): string[] {
  if (delimiter === ",") {
    return line.split(",").map((cell) => cleanCell(cell));
  }
  return line.split(delimiter).map((cell) => cleanCell(cell));
}

function looksLikeHeader(cells: string[]): boolean {
  if (cells.length === 0) return false;
  const joined = cells.join(" ").toLowerCase();
  return HEADER_PATTERN.test(joined);
}

export function isBulkRowEmpty(row: Pick<BulkOrderLineDraft, "boschArticle" | "quantity" | "unitPrice">): boolean {
  return !row.boschArticle.trim() && !row.quantity.trim() && !row.unitPrice.trim();
}

export function createEmptyBulkOrderLineRow(id?: string): BulkOrderLineDraft {
  return {
    id: id ?? crypto.randomUUID(),
    boschArticle: "",
    quantity: "",
    unitPrice: "",
  };
}

export function createEmptyBulkOrderLineGrid(count = DEFAULT_EMPTY_ROWS): BulkOrderLineDraft[] {
  return Array.from({ length: count }, () => createEmptyBulkOrderLineRow());
}

function validateRow(
  rowIndex: number,
  boschArticle: string,
  quantity: number | null,
  unitPrice: number | null,
): ParsedBulkOrderLine {
  const article = boschArticle.trim();
  const qty = quantity ?? NaN;
  const price = unitPrice ?? 0;

  if (!article) {
    return { rowIndex, boschArticle: article, quantity: qty, unitPrice: price, valid: false, error: "Code article manquant" };
  }
  if (!Number.isFinite(qty) || qty <= 0) {
    return { rowIndex, boschArticle: article, quantity: qty, unitPrice: price, valid: false, error: "Quantité invalide" };
  }
  if (!Number.isFinite(price) || price < 0) {
    return { rowIndex, boschArticle: article, quantity: qty, unitPrice: price, valid: false, error: "P.U. invalide" };
  }
  return { rowIndex, boschArticle: article, quantity: qty, unitPrice: price, valid: true };
}

export function validateBulkOrderLineDraft(
  rowIndex: number,
  row: Pick<BulkOrderLineDraft, "boschArticle" | "quantity" | "unitPrice">,
): ParsedBulkOrderLine {
  if (isBulkRowEmpty(row)) {
    return {
      rowIndex,
      boschArticle: "",
      quantity: NaN,
      unitPrice: 0,
      valid: false,
      error: "Ligne vide",
    };
  }
  return validateRow(
    rowIndex,
    row.boschArticle,
    parseNumber(row.quantity),
    row.unitPrice.trim() ? parseNumber(row.unitPrice) : 0,
  );
}

export function parseBulkOrderLinesText(text: string): ParsedBulkOrderLine[] {
  const rawLines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (rawLines.length === 0) return [];

  const delimiter = detectDelimiter(rawLines[0]!);
  let startIndex = 0;
  const firstCells = splitRow(rawLines[0]!, delimiter);
  if (looksLikeHeader(firstCells)) {
    startIndex = 1;
  }

  const parsed: ParsedBulkOrderLine[] = [];
  for (let i = startIndex; i < rawLines.length; i += 1) {
    const cells = splitRow(rawLines[i]!, delimiter);
    if (cells.every((cell) => !cell)) continue;

    const boschArticle = cells[0] ?? "";
    const quantity = cells.length >= 2 ? parseNumber(cells[1] ?? "") : null;
    const unitPrice = cells.length >= 3 ? parseNumber(cells[2] ?? "") : 0;

    parsed.push(validateRow(i + 1, boschArticle, quantity, unitPrice));
  }

  return parsed;
}

export function bulkRowsFromParsedText(text: string): BulkOrderLineDraft[] {
  const parsed = parseBulkOrderLinesText(text);
  if (parsed.length === 0) return createEmptyBulkOrderLineGrid();

  return parsed.map((row) => ({
    id: crypto.randomUUID(),
    boschArticle: row.boschArticle,
    quantity: Number.isFinite(row.quantity) ? String(row.quantity) : "",
    unitPrice: Number.isFinite(row.unitPrice) ? String(row.unitPrice) : "",
  }));
}

export function evaluateBulkOrderLineGrid(rows: BulkOrderLineDraft[]): {
  rowStatuses: ParsedBulkOrderLine[];
  validLines: ParsedBulkOrderLine[];
  invalidCount: number;
} {
  const rowStatuses = rows.map((row, index) => validateBulkOrderLineDraft(index + 1, row));
  const nonEmpty = rowStatuses.filter((_, index) => !isBulkRowEmpty(rows[index]!));
  const validLines = nonEmpty.filter((row) => row.valid);
  return {
    rowStatuses,
    validLines,
    invalidCount: nonEmpty.length - validLines.length,
  };
}
