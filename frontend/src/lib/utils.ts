import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number, currency = "EUR"): string {
  return new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency,
  }).format(amount);
}

export function formatDate(date: string | Date | null | undefined): string {
  if (!date) return "-";
  if (typeof date === "string") {
    const match = date.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (match) {
      const [, year, month, day] = match;
      return new Intl.DateTimeFormat("fr-FR", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      }).format(new Date(Number(year), Number(month) - 1, Number(day)));
    }
  }
  const d = typeof date === "string" ? new Date(date) : date;
  if (isNaN(d.getTime())) return "Invalid Date";
  return new Intl.DateTimeFormat("fr-FR").format(d);
}

export function resolveDisplayTimeZone(timeZone?: string | null): string | undefined {
  const value = (timeZone || "").trim();
  if (!value) return undefined;
  if (value.includes("/")) {
    const direct = value.match(/[A-Za-z_]+\/[A-Za-z_]+(?:\/[A-Za-z_]+)?$/);
    if (direct) return direct[0];
  }
  const afterParen = value.replace(/^.*\)\s*/, "").trim();
  if (afterParen.includes("/")) {
    const direct = afterParen.match(/[A-Za-z_]+\/[A-Za-z_]+(?:\/[A-Za-z_]+)?$/);
    if (direct) return direct[0];
  }
  return undefined;
}

export function formatDateTime(date: string | Date | null | undefined, timeZone?: string | null): string {
  if (!date) return "-";
  const d = typeof date === "string" ? new Date(date) : date;
  if (isNaN(d.getTime())) return "-";
  const resolvedTimeZone = resolveDisplayTimeZone(timeZone);
  return new Intl.DateTimeFormat("fr-FR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    ...(resolvedTimeZone ? { timeZone: resolvedTimeZone } : {}),
  }).format(d);
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} Mo`;
}

export function confidenceColor(confidence: number): string {
  if (confidence >= 90) return "text-emerald-600";
  if (confidence >= 75) return "text-amber-600";
  return "text-red-600";
}

export function downloadTextFile(content: string, fileName: string): void {
  const blob = new Blob([content], { type: "application/edifact;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}
