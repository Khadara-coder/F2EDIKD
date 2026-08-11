export interface ParsedBulkOrderLine {
  rowIndex: number;
  boschArticle: string;
  quantity: number;
  unitPrice: number;
  valid: boolean;
  error?: string;
}

const HEADER_PATTERN = /^(code|article|r[eé]f|matnr|qt[eé]|qty|quantit|p\.?u|prix|unit)/i;

function detectDelimiter(line: string): string {
  if (line.includes("\t")) return "\t";
  if (line.includes(";")) return ";";
  if (line.includes(",")) return ",";
  return "\t";
}

function parseNumber(raw: string): number | null {
  const normalized = raw.trim().replace(/\s/g, "").replace(",", ".");
  if (!normalized) return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

function splitRow(line: string, delimiter: string): string[] {
  if (delimiter === ",") {
    return line.split(",").map((cell) => cell.trim());
  }
  return line.split(delimiter).map((cell) => cell.trim());
}

function looksLikeHeader(cells: string[]): boolean {
  if (cells.length === 0) return false;
  const joined = cells.join(" ").toLowerCase();
  return HEADER_PATTERN.test(joined);
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
    const cells = splitRow(rawLines[i]!, delimiter).filter((cell, idx, arr) => cell !== "" || idx < arr.length);
    if (cells.length === 0) continue;

    const boschArticle = cells[0] ?? "";
    const quantity = cells.length >= 2 ? parseNumber(cells[1] ?? "") : null;
    const unitPrice = cells.length >= 3 ? parseNumber(cells[2] ?? "") : 0;

    parsed.push(validateRow(i + 1, boschArticle, quantity, unitPrice));
  }

  return parsed;
}
