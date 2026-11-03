import {
  ITEM_CAPACITY,
  classCapacity,
  displayPercent,
  statusFor,
  type StockStatus,
} from "./stockStatus";
import type { InventorySnapshot } from "../types";

export interface AggregatedClassStat {
  code: string;
  name: string;
  quantity: number;
  capacity: number;
  status: StockStatus;
  fill: number;
}

export interface InventoryAggregateStats {
  totalQuantity: number;
  totalCapacity: number;
  totalStatus: StockStatus;
  totalFill: number;
  classes: AggregatedClassStat[];
}

export function aggregateInventoryStats(snapshots: InventorySnapshot[]): InventoryAggregateStats {
  const merged = new Map<string, { code: string; name: string; quantity: number; capacity: number }>();

  for (const snapshot of snapshots) {
    for (const row of snapshot.classes) {
      const cap = classCapacity(row);
      const existing = merged.get(row.code);
      if (existing) {
        existing.quantity += row.quantity;
        existing.capacity += cap;
      } else {
        merged.set(row.code, {
          code: row.code,
          name: row.name,
          quantity: row.quantity,
          capacity: cap,
        });
      }
    }
  }

  const classes = [...merged.values()].map((row) => ({
    ...row,
    status: statusFor(row.quantity, row.capacity),
    fill: displayPercent(row.quantity, row.capacity),
  }));

  const goods = classes.filter((row) => row.code !== "fund");
  const totalQuantity = goods.reduce((sum, row) => sum + row.quantity, 0);
  const totalCapacity =
    goods.reduce((sum, row) => sum + row.capacity, 0) || ITEM_CAPACITY * 3;
  const totalStatus = statusFor(totalQuantity, totalCapacity);
  const totalFill = displayPercent(totalQuantity, totalCapacity);

  return { totalQuantity, totalCapacity, totalStatus, totalFill, classes };
}

export function toneClassForCategory(code: string): string {
  if (code === "clothing") return "tone-clothes";
  if (code === "foods") return "tone-foods";
  if (code === "kitchenware") return "tone-kitchenware";
  if (code === "utilities") return "tone-utility";
  if (code === "fund") return "tone-fund";
  return "tone-total";
}
