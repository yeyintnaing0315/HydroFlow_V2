import { ALLOCATION_SKU_COLUMNS, allocationSkuKey } from "./allocationCatalog";
import type { AllocationLineItem, AllocationTownshipRow } from "../types";

export type PlanDeductionLine = Pick<
  AllocationLineItem,
  "category_code" | "item_code" | "name" | "unit" | "allocated"
>;

/** Sum allocated quantities per SKU across plan rows (depot stock deducted on confirm). */
export function aggregatePlanDeductions(rows: AllocationTownshipRow[]): PlanDeductionLine[] {
  const totals = new Map<string, PlanDeductionLine>();

  for (const row of rows) {
    for (const item of row.line_items ?? []) {
      const allocated = Number(item.allocated);
      if (!Number.isFinite(allocated) || allocated <= 0) continue;
      const key = allocationSkuKey(item.category_code, item.item_code);
      const existing = totals.get(key);
      if (existing) {
        existing.allocated += allocated;
      } else {
        totals.set(key, {
          category_code: item.category_code,
          item_code: item.item_code,
          name: item.name,
          unit: item.unit,
          allocated,
        });
      }
    }
  }

  const ordered: PlanDeductionLine[] = [];
  for (const column of ALLOCATION_SKU_COLUMNS) {
    const key = allocationSkuKey(column.category_code, column.item_code);
    const line = totals.get(key);
    if (line) ordered.push(line);
  }
  for (const [key, line] of totals) {
    if (!ordered.some((entry) => allocationSkuKey(entry.category_code, entry.item_code) === key)) {
      ordered.push(line);
    }
  }
  return ordered;
}
