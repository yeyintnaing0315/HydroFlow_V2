import type { AllocationPlanResponse, AllocationTownshipRow } from "../types";
import { ALLOCATION_SKU_COLUMNS, allocationSkuKey } from "./allocationCatalog";
import { formatAllocatedRequested } from "./allocationPerPersonCheck";

export function supplyItemColumns(_rows?: AllocationTownshipRow[]) {
  return ALLOCATION_SKU_COLUMNS.map((column) => [
    allocationSkuKey(column.category_code, column.item_code),
    { name: column.name, unit: column.unit },
  ] as const);
}

export function buildSupplyTable(plan: AllocationPlanResponse): { head: string[]; body: string[][] } {
  const rows = plan.rows;
  const itemColumns = supplyItemColumns();
  const head = [
    "Township",
    "Male",
    "Female",
    "People",
    ...itemColumns.map(([, meta]) => `${meta.name} (${meta.unit})`),
  ];
  const body = rows.map((row) => {
    const itemByKey = new Map(
      row.line_items.map((item) => [allocationSkuKey(item.category_code, item.item_code), item]),
    );
    return [
      row.township_name,
      String(row.affected_male ?? 0),
      String(row.affected_female ?? 0),
      String(row.population),
      ...itemColumns.map(([key]) => {
        const item = itemByKey.get(key);
        if (!item || (item.allocated <= 0 && item.requested <= 0)) return "—";
        return formatAllocatedRequested(item.allocated, item.requested);
      }),
    ];
  });
  return { head, body };
}
