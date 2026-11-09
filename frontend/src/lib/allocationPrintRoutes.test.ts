import { describe, expect, it } from "vitest";
import { printMapRoutes } from "./allocationPrintRoutes";
import type { AllocationPlanResponse, Coordinates } from "../types";

const road: Coordinates[] = [
  { latitude: 18.817, longitude: 95.217 },
  { latitude: 18.7, longitude: 95.35 },
  { latitude: 18.55, longitude: 95.44 },
  { latitude: 18.489, longitude: 95.507 },
];

const plan: AllocationPlanResponse = {
  plan_id: "1",
  planning_date: "2026-11-02",
  warehouse: { id: "depot-west", name: "Pyay depot (west)", region: "west", latitude: 18.817, longitude: 95.217 },
  warehouses: [
    { id: "depot-west", name: "Pyay depot (west)", region: "west", latitude: 18.817, longitude: 95.217 },
  ],
  totals: { affected_population: 100, available_stock_units: 0, resources_needed_units: 0 },
  rows: [
    {
      township_id: "paungde",
      township_name: "Paungde",
      latitude: 18.64,
      longitude: 95.62,
      population: 100,
      priority: "high",
      resources_label: "Rice",
      quantities_label: "1 bag",
      route_id: "Route A",
      depot_region: "west",
      has_shortage: false,
      line_items: [],
    },
  ],
  shortages: [],
  routes: [],
  model_version: "test",
  disclaimer: "test",
};

describe("printMapRoutes", () => {
  it("draws the same road the plan map already loaded", () => {
    const model = printMapRoutes(plan, "single", null, {
      paungde: { path: road, distanceM: 99_300 },
    });
    expect(model.routes[0].path).toEqual(road);
    expect(model.routes[0].distanceM).toBe(99_300);
  });

  it("uses a saved single-stop road when the live preview is not ready", () => {
    const saved = {
      ...plan,
      routes: [
        {
          route_id: "Route A",
          stop_count: 1,
          depot_region: "west" as const,
          path: road,
          distance_m: 88_000,
          routing_method: "osrm_road",
          plan: null,
        },
      ],
    };
    const model = printMapRoutes(saved, "single");
    expect(model.routes[0].path).toEqual(road);
    expect(model.routes[0].distanceM).toBe(88_000);
  });

  it("does not reuse a shared multi-stop corridor as each township line", () => {
    const shared = {
      ...plan,
      rows: [
        plan.rows[0],
        {
          ...plan.rows[0],
          township_id: "shwedaung",
          township_name: "Shwedaung",
        },
      ],
      routes: [
        {
          route_id: "Route A",
          stop_count: 2,
          depot_region: "west" as const,
          path: [
            { latitude: 18.817, longitude: 95.217 },
            { latitude: 99, longitude: 99 },
            { latitude: 18.817, longitude: 95.217 },
          ],
          routing_method: "osrm_road",
          plan: null,
        },
      ],
    };
    const model = printMapRoutes(shared, "single");
    expect(model.routes).toHaveLength(2);
    expect(model.routes[0].path).toHaveLength(2);
    expect(model.routes[1].path).toHaveLength(2);
    expect(model.routes.some((route) => route.path.some((point) => point.latitude === 99))).toBe(false);
  });

  it("hides the straight fallback while the road is still loading", () => {
    const model = printMapRoutes(plan, "single", null, {}, true);
    expect(model.routes[0].path).toEqual([]);
  });
});
