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
  totals: { affected_population: 20, available_stock_units: 100, resources_needed_units: 20010 },
  shortages: [],
  routes: [],
  model_version: "allocation-per-person",
  disclaimer: "Academic allocation illustration.",
  status: "confirmed",
  rows: [
    {
      township_id: "bago",
      township_name: "Bago",
      latitude: 17.33,
      longitude: 96.48,
      population: 20,
      affected_male: 9,
      affected_female: 11,
      priority: "high",
      resources_label: "Rice",
      quantities_label: "10 bag",
      route_id: "Route A",
      depot_region: "east",
      has_shortage: false,
      line_items: [
        { category_code: "foods", item_code: "rice", name: "Rice", unit: "bag", requested: 20, allocated: 20 },
        { category_code: "clothing", item_code: "m_longyi", name: "Men longyi", unit: "piece", requested: 9, allocated: 9 },
        { category_code: "clothing", item_code: "f_longyi", name: "Women longyi", unit: "piece", requested: 11, allocated: 11 },
      ],
    },
  ],
};

describe("buildAllocationReport", () => {
  it("builds a single supply table for print", () => {
    const report = buildAllocationReport(plan);
    expect(report.title).toBe("Resource allocation plan");
    expect(report.subtitle).toContain("2026-10-20");
    expect(report.subtitle).toContain("Confirmed");
    expect(report.tableHead[0]).toBe("Township");
    expect(report.tableHead).toContain("Male");
    expect(report.tableBody[0][0]).toBe("Bago");
    expect(report.tableBody[0]).toContain("9");
    expect(report.tableBody[0]).toContain("11");
    expect(report.filename).toBe("allocation-plan-2026-10-20-p-1.pdf");
  });
});
