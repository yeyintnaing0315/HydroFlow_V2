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
    const slip = report.slips[0];
    expect(slip.townshipName).toBe("Bago");
    expect(slip.male).toBe("9");
    expect(slip.female).toBe("11");
    expect(slip.people).toBe("20");
    const foods = slip.groups.find((group) => group.id === "foods");
    const clothing = slip.groups.find((group) => group.id === "clothing");
    expect(foods?.lines.find((line) => line.name === "Rice")?.detail).toBe("20 bags");
    expect(clothing?.lines.find((line) => line.name === "Men longyi")?.detail).toBe("9 pieces");
    expect(clothing?.lines.find((line) => line.name === "Women longyi")?.detail).toBe("11 pieces");
    expect(slip.groups.flatMap((group) => group.lines).some((line) => line.name === "Box")).toBe(true);
    expect(report.filename).toBe("allocation-plan-2026-10-20-p-1.pdf");
  });
});
