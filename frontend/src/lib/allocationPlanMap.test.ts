import { describe, expect, it } from "vitest";
import { routePathForTownship, routesFromPlan, townshipsFromPlan } from "./allocationPlanMap";
import type { AllocationPlanResponse } from "../types";

const basePlan: AllocationPlanResponse = {
  plan_id: "1",
  planning_date: "2026-11-02",
  warehouse: { id: "depot-west", name: "Pyay depot (west)", region: "west", latitude: 0, longitude: 0 },
  warehouses: [
    { id: "depot-east", name: "Bago depot (east)", region: "east", latitude: 0, longitude: 0 },
    { id: "depot-west", name: "Pyay depot (west)", region: "west", latitude: 0, longitude: 0 },
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

describe("allocationPlanMap", () => {
  it("uses town-seat coordinates instead of stale plan row points", () => {
    const townships = townshipsFromPlan(basePlan);
    expect(townships[0].latitude).toBeCloseTo(18.48947, 3);
    expect(townships[0].longitude).toBeCloseTo(95.50721, 3);
  });

  it("draws fallback legs to resolved town seats", () => {
    const depots = [
      {
        id: "depot-west",
        name: "Pyay",
        region: "west" as const,
        latitude: 18.817,
        longitude: 95.217,
      },
    ];
    const routes = routesFromPlan(basePlan, depots);
    const last = routes[0].path[routes[0].path.length - 1];
    expect(last.latitude).toBeCloseTo(18.48947, 3);
    expect(last.longitude).toBeCloseTo(95.50721, 3);
  });

  it("gives each township its own depot leg when they share a route", () => {
    const shared = {
      ...basePlan,
      rows: [
        basePlan.rows[0],
        {
          ...basePlan.rows[0],
          township_id: "shwedaung",
          township_name: "Shwedaung",
          latitude: 18.7,
          longitude: 95.2,
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
          distance_m: 999_000,
          plan: null,
        },
      ],
    };
    const depots = [
      {
        id: "depot-west",
        name: "Pyay",
        region: "west" as const,
        latitude: 18.817,
        longitude: 95.217,
      },
    ];
    const routes = routesFromPlan(shared, depots);
    expect(routes).toHaveLength(2);
    expect(routes[0].path).not.toEqual(routes[1].path);
    expect(routes[0].distanceM).toBeNull();
    expect(routes[1].distanceM).toBeNull();
    expect(routes[0].path.some((point) => point.latitude === 99)).toBe(false);
    expect(routes[1].path.some((point) => point.latitude === 99)).toBe(false);
    expect(routes[0].path[0]).toEqual({ latitude: 18.817, longitude: 95.217 });
    expect(routes[1].path[0]).toEqual({ latitude: 18.817, longitude: 95.217 });
    expect(routes[1].path[routes[1].path.length - 1].latitude).toBeCloseTo(18.7051, 3);
  });

  it("does not extend a route with a long straight connector", () => {
    const loop = [
      { latitude: 17.335, longitude: 96.481 },
      { latitude: 18.74, longitude: 96.52 },
      { latitude: 17.335, longitude: 96.481 },
    ];
    expect(routePathForTownship(loop, { latitude: 18.74, longitude: 96.52 })).toEqual(loop);
    const joined = routePathForTownship(
      [
        { latitude: 17.335, longitude: 96.481 },
        { latitude: 18.74, longitude: 96.52 },
      ],
      { latitude: 18.741, longitude: 96.521 },
    );
    expect(joined[joined.length - 1]).toEqual({ latitude: 18.741, longitude: 96.521 });
  });
});
