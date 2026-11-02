export type TimeMode = "past" | "today" | "future";

const YANGON = "Asia/Yangon";

export function localToday(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: YANGON,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;
  return `${year}-${month}-${day}`;
}

export function addDays(isoDate: string, offset: number): string {
  const parts = isoDate.split("-").map(Number);
  const day = new Date(parts[0], parts[1] - 1, parts[2]);
  day.setDate(day.getDate() + offset);
  const y = day.getFullYear();
  const m = String(day.getMonth() + 1).padStart(2, "0");
  const d = String(day.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function daysInRange(start: string, end: string): string[] {
  const out: string[] = [];
  let cursor = start;
  while (cursor <= end) {
    out.push(cursor);
    cursor = addDays(cursor, 1);
  }
  return out;
}

export const DEFAULT_HISTORY_START = "2010-01-01";

export function forecastEnd(asOf: string = localToday(), horizonDays = 7): string {
  return addDays(asOf, horizonDays);
}

export function filterDaysByMode(asOf: string, mode: TimeMode): { start: string; end: string } {
  if (mode === "past") {
    return { start: addDays(asOf, -7), end: addDays(asOf, -1) };
  }
  if (mode === "future") {
    return { start: addDays(asOf, 1), end: addDays(asOf, 7) };
  }
  return { start: asOf, end: asOf };
}
