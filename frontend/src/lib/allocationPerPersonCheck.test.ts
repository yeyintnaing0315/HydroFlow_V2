import { describe, expect, it } from "vitest";
import { formatAllocatedRequested, rowHasPerPersonRuleMismatch } from "./allocationPerPersonCheck";
import type { AllocationTownshipRow } from "../types";

function row(people: number, items: AllocationTownshipRow["line_items"]): AllocationTownshipRow {
  return {
    township_id: "waw",
    township_name: "Waw",
    latitude: 0,
    longitude: 0,
    population: people,
    affected_male: 461,
    affected_female: 539,
    priority: "severe",
    resources_label: "",
    quantities_label: "",
    route_id: "Route A",
    depot_region: "west",
    has_shortage: false,
    line_items: items,
  };
}

describe("allocationPerPersonCheck", () => {
  it("detects rice count mismatch", () => {
    const mismatch = rowHasPerPersonRuleMismatch(
      row(1000, [
        {
          category_code: "foods",
          item_code: "rice",
          name: "Rice",
          unit: "bag",
          requested: 999,
          allocated: 999,
        },
      ]),
    );
    expect(mismatch).toBe(true);
  });

  it("formats equal allocated and requested as a single number", () => {
    expect(formatAllocatedRequested(1000, 1000)).toBe("1,000");
  });

  it("formats partial allocation with slash", () => {
    expect(formatAllocatedRequested(10, 20)).toBe("10 / 20");
  });
});
