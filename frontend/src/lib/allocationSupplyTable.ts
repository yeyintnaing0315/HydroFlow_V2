import type { AllocationPlanResponse, AllocationTownshipRow } from "../types";
import { ALLOCATION_SKU_COLUMNS, type AllocationSkuColumn as CatalogSku, allocationSkuKey } from "./allocationCatalog";
import { formatAllocatedRequested } from "./allocationPerPersonCheck";

/** Physical relief goods. Fund is listed with the people counts. */
export const RELIEF_ITEM_COUNT = ALLOCATION_SKU_COLUMNS.filter((column) => column.category_code !== "fund").length;

export interface SupplyLine {
  name: string;
  detail: string;
}

export interface SupplyGroup {
  id: string;
  title: string;
  /** Left column holds the short lists. Kitchen sits on the right so the page stays balanced. */
  column: "left" | "right";
  lines: SupplyLine[];
}

export interface TownshipSlip {
  townshipName: string;
  male: string;
  female: string;
  people: string;
  fund: string;
  groups: SupplyGroup[];
}

const SLIP_GROUPS: {
  id: string;
  title: string;
  column: "left" | "right";
  match: (column: CatalogSku) => boolean;
}[] = [
  { id: "foods", title: "Food", column: "left", match: (column) => column.category_code === "foods" },
  { id: "clothing", title: "Clothing", column: "left", match: (column) => column.category_code === "clothing" },
  {
    id: "household",
    title: "Household",
    column: "left",
    match: (column) => column.category_code === "utilities",
  },
  {
    id: "kitchen",
    title: "Kitchen",
    column: "right",
    match: (column) => column.category_code === "kitchenware",
  },
];

function spokenUnit(unit: string, amount: string): string {
  if (amount === "1") return unit;
  const plurals: Record<string, string> = {
    bag: "bags",
    bottle: "bottles",
    can: "cans",
    piece: "pieces",
    pack: "packs",
    box: "boxes",
  };
  return plurals[unit] ?? unit;
}

function lineDetail(row: AllocationTownshipRow, column: CatalogSku): string {
  const item = row.line_items.find(
    (entry) => allocationSkuKey(entry.category_code, entry.item_code) === allocationSkuKey(column.category_code, column.item_code),
  );
  if (!item || (item.allocated <= 0 && item.requested <= 0)) return "—";
  const amount = formatAllocatedRequested(item.allocated, item.requested);
  return `${amount} ${spokenUnit(column.unit, amount)}`;
}

function fundDetail(row: AllocationTownshipRow): string {
  const item = row.line_items.find((entry) => entry.category_code === "fund" && entry.item_code == null);
  if (!item || (item.allocated <= 0 && item.requested <= 0)) return "—";
  return `${formatAllocatedRequested(item.allocated, item.requested)} MMK`;
}

/** One plain list per township, readable without a wide table. */
export function buildTownshipSlips(plan: AllocationPlanResponse): TownshipSlip[] {
  return plan.rows.map((row) => ({
    townshipName: row.township_name,
    male: (row.affected_male ?? 0).toLocaleString(),
    female: (row.affected_female ?? 0).toLocaleString(),
    people: row.population.toLocaleString(),
    fund: fundDetail(row),
    groups: SLIP_GROUPS.map((group) => ({
      id: group.id,
      title: group.title,
      column: group.column,
      lines: ALLOCATION_SKU_COLUMNS.filter(group.match).map((column) => ({
        name: column.name,
        detail: lineDetail(row, column),
      })),
    })),
  }));
}
