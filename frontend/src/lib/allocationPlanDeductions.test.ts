import { describe, expect, it } from "vitest";
import { aggregatePlanDeductions } from "./allocationPlanDeductions";
import type { AllocationTownshipRow } from "../types";

describe("aggregatePlanDeductions", () => {
  it("sums allocated quantities per SKU across townships", () => {
    const rows: AllocationTownshipRow[] = [
      {
        township_id: "a",
        township_name: "A",
        latitude: 0,
        longitude: 0,
        population: 10,
        priority: "high",
        resources_label: "",
        quantities_label: "",
        route_id: "r1",
        depot_region: "east",
        has_shortage: false,
        line_items: [
          { category_code: "foods", item_code: "rice", name: "Rice", unit: "bag", requested: 5, allocated: 5 },
          { category_code: "foods", item_code: "oil", name: "Oil", unit: "bottle", requested: 2, allocated: 0 },
        ],
      },
      {
        township_id: "b",
        township_name: "B",
        latitude: 0,
        longitude: 0,
        population: 10,
        priority: "severe",
        resources_label: "",
        quantities_label: "",
        route_id: "r1",
        depot_region: "east",
        has_shortage: false,
        line_items: [
          { category_code: "foods", item_code: "rice", name: "Rice", unit: "bag", requested: 3, allocated: 3 },
        ],
      },
    ];

    const lines = aggregatePlanDeductions(rows);
    expect(lines).toHaveLength(1);
    expect(lines[0].name).toBe("Rice");
    expect(lines[0].allocated).toBe(8);
  });
});
