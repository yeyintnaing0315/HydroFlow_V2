import type { InventoryClass } from "../types";

export type StockStatus = "Out of Stock" | "Critical" | "Low Stock" | "In Stock" | "Full";

export const ITEM_CAPACITY = 100_000;
export const FUND_CAPACITY = 10_000_000_000;

export const STATUS_RANK: Record<StockStatus, number> = {
  "Out of Stock": 0,
  Critical: 1,
  "Low Stock": 2,
  "In Stock": 3,
  Full: 4,
};

export function itemCapacity(classCode: string, item?: { capacity?: number }): number {
  if (item?.capacity && item.capacity > 0) return item.capacity;
  return classCode === "fund" ? FUND_CAPACITY : ITEM_CAPACITY;
}

export function classCapacity(row: InventoryClass): number {
  if (row.capacity && row.capacity > 0) return row.capacity;
  if (row.code === "fund") return FUND_CAPACITY;
  return row.items.length * ITEM_CAPACITY;
}

export function fillRatio(quantity: number, capacity: number): number {
  if (quantity <= 0 || capacity <= 0) return 0;
  return (quantity / capacity) * 100;
}

export function displayPercent(quantity: number, capacity: number): number {
  const ratio = fillRatio(quantity, capacity);
  if (ratio <= 0) return 0;
  const rounded = Math.round(ratio);
  return Math.min(100, rounded === 0 ? 1 : rounded);
}

export function statusFor(quantity: number, capacity: number): StockStatus {
  if (quantity <= 0) return "Out of Stock";
  const ratio = fillRatio(quantity, capacity);
  if (ratio < 30) return "Critical";
  if (ratio < 60) return "Low Stock";
  if (ratio < 100) return "In Stock";
  return "Full";
}

export function statusSlug(status: StockStatus): string {
  return status.replace(/\s+/g, "-").toLowerCase();
}
