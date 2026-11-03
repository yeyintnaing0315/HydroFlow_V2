import type { AllocationLineItem, AllocationTownshipRow } from "../types";

/** Matches backend `allocation_rules.FUND_MMK_PER_PERSON`. */
export const FUND_MMK_PER_PERSON = 10_000;

const PER_PERSON_SKUS: Set<string> = new Set([
  "foods:rice",
  "foods:canned_fish",
  "foods:oil",
  "utilities:blanket",
  "kitchenware:water_dipper",
  "clothing:tshirt",
]);

function skuKey(categoryCode: string, itemCode: string | null): string {
  return `${categoryCode}:${itemCode ?? ""}`;
}

function expectedRequested(item: AllocationLineItem, people: number): number | null {
  const key = skuKey(item.category_code, item.item_code);
  if (item.category_code === "fund" && item.item_code == null) {
    return people * FUND_MMK_PER_PERSON;
  }
  if (PER_PERSON_SKUS.has(key)) {
    return people;
  }
  if (item.category_code === "clothing" && (item.item_code === "m_longyi" || item.item_code === "f_longyi")) {
    return null;
  }
  return null;
}

/** True when any line item requested amount does not match the per-person planning rule. */
export function rowHasPerPersonRuleMismatch(row: AllocationTownshipRow): boolean {
  const people = Math.max(0, Math.round(row.population));
  if (people <= 0) return false;

  let longyiRequested = 0;
  for (const item of row.line_items) {
    if (item.requested <= 0) continue;
    const expected = expectedRequested(item, people);
    if (expected != null && Math.round(item.requested) !== expected) {
      return true;
    }
    if (item.category_code === "clothing" && (item.item_code === "m_longyi" || item.item_code === "f_longyi")) {
      longyiRequested += Math.round(item.requested);
    }
  }
  if (longyiRequested > 0 && longyiRequested !== people) {
    return true;
  }
  return false;
}

export function formatAllocatedRequested(allocated: number, requested: number): string {
  const a = allocated.toLocaleString();
  if (Math.round(allocated) === Math.round(requested)) {
    return a;
  }
  return `${a} / ${requested.toLocaleString()}`;
}
