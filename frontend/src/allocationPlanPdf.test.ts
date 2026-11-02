import { describe, expect, it } from "vitest";
import { buildAllocationReport } from "./allocationPlanPdf";
import type { AllocationPlanResponse } from "./types";

const plan: AllocationPlanResponse = {
  plan_id: "p/1",
  planning_date: "2026-10-20",
  warehouse: { id: "depot-bago", name: "Bago depot (east)", region: "east", latitude: 17.3, longitude: 96.4 },
  warehouses: [
    { id: "depot-bago", name: "Bago depot (east)", region: "east", latitude: 17.3, longitude: 96.4 },
  ],
  totals: { affected_population: 30, available_stock_units: 100, resources_needed_units: 20010 },
  shortages: [
    {
      category_code: "fund",
      item_code: null,
      name: "Fund",
      unit: "mmk",
      requested: 20000,
      available: 0,
      unmet: 20000,
      depot_region: "east",
    },
  ],
  routes: [],
  model_version: "allocation-v3",
  disclaimer: "Academic allocation illustration.",
  rows: [
    {
      township_id: "bago",
      township_name: "Bago",
      latitude: 17.33,
      longitude: 96.48,
      population: 20,
      priority: "high",
      resources_label: "Rice",
      quantities_label: "10 bag",
      route_id: "Route A",
      depot_region: "east",
      has_shortage: true,
      line_items: [
        { category_code: "foods", item_code: "rice", name: "Rice", unit: "bag", requested: 20, allocated: 10 },
        { category_code: "fund", item_code: null, name: "Fund", unit: "mmk", requested: 20000, allocated: 0 },
      ],
    },
  ],
};

describe("buildAllocationReport", () => {
  it("keeps each item in its own unit and does not add bags to kyat", () => {
    const report = buildAllocationReport(plan);
    expect(report.summary).toBe("Affected people: 30 · Townships: 1 · Shortage lines: 1");
    expect(report.summary).not.toContain("20,010");
    expect(report.townshipHead).not.toContain("Requested");
    expect(report.townshipBody[0]).toEqual(["Bago", "Bago depot (east)", "20", "high", "Route A"]);
    const fund = (20000).toLocaleString();
    expect(report.itemBody).toEqual([
      ["Bago", "Rice", "bag", "20", "10"],
      ["Bago", "Fund", "MMK", fund, "0"],
    ]);
    expect(report.shortageBody[0]).toEqual(["Fund", "MMK", "Bago depot (east)", fund, "0", fund]);
    expect(report.filename).toBe("allocation-plan-2026-10-20-p-1.pdf");
  });
});
