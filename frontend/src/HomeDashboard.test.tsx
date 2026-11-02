import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import HomeDashboard from "./HomeDashboard";
import type {
  AllocationPlanResponse,
  BagoAreasResponse,
  InventorySnapshot,
  RegionForecastResponse,
  RegionForecastScore,
} from "./types";

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  CircleMarker: () => null,
  Popup: () => null,
  GeoJSON: () => null,
  Pane: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  useMap: () => ({
    fitBounds: () => undefined,
    invalidateSize: () => undefined,
    getSize: () => ({ x: 800, y: 600 }),
    getContainer: () => document.createElement("div"),
  }),
}));

vi.mock("./api", () => ({
  api: {
    predictionRegionForecast: vi.fn(),
    allocationPlans: vi.fn(),
    allocationPlanDetail: vi.fn(),
    inventoryLocations: vi.fn(),
  },
}));

const areas: BagoAreasResponse = {
  latitude: 18.26,
  longitude: 96.07,
  source: "test",
  dataset_version: "1",
  license: "",
  coverage_note: "",
  region_id: "bago",
  region_name_en: "Bago",
  region_name_local: "Bago",
  districts: [
    {
      id: "d1",
      slug: "bago",
      name_en: "Bago",
      name_local: "Bago",
      latitude: 17.3,
      longitude: 96.4,
      level: 2,
      area_type: "district",
      coverage_status: "complete",
      townships: [
        {
          id: "t1",
          slug: "bago-town",
          name_en: "Bago",
          name_local: "Bago",
          latitude: 17.33,
          longitude: 96.48,
          level: 3,
          area_type: "township",
          coverage_status: "complete",
        },
      ],
    },
  ],
};

function score(
  overrides: Partial<RegionForecastScore> & Pick<RegionForecastScore, "township_id" | "township_name" | "lead_days">,
): RegionForecastScore {
  return {
    district_id: "d1",
    latitude: 17.33,
    longitude: 96.48,
    target_date: "2026-10-31",
    flood_probability: 0.2,
    risk_band: "low",
    probability_risk_level: "low",
    risk_level: "low",
    rainfall_mm: 10,
    discharge_m3_s: 100,
    static_hazard: null,
    early_warning: false,
    warning_reason: null,
    warning_level: null,
    drivers: { rain: "low", discharge: "low", floodplain_or_river_distance: "far" },
    data_status: "model_estimate",
    ...overrides,
  };
}

const forecast: RegionForecastResponse = {
  as_of: "2026-10-31",
  run_id: 1,
  model_version: "test",
  feature_version: "v2",
  disclaimer: "Academic estimate.",
  cached: true,
  labels_found: false,
  label_file: null,
  missing_inputs: [],
  scores: [
    score({
      township_id: "t1",
      township_name: "Bago",
      lead_days: 0,
      flood_probability: 0.82,
      risk_band: "very_high",
      probability_risk_level: "severe",
      risk_level: "severe",
      rainfall_mm: 40,
      discharge_m3_s: 1200,
      early_warning: true,
      warning_level: "severe",
      district_id: "d1",
    }),
    score({
      township_id: "t1",
      township_name: "Bago",
      lead_days: 1,
      target_date: "2026-11-01",
      flood_probability: 0.4,
      risk_band: "moderate",
      probability_risk_level: "moderate",
      risk_level: "moderate",
      rainfall_mm: 80,
      discharge_m3_s: 900,
    }),
    score({
      township_id: "t2",
      township_name: "Pyay",
      district_id: "d2",
      latitude: 18.82,
      longitude: 95.22,
      lead_days: 0,
      flood_probability: 0.61,
      risk_band: "high",
      probability_risk_level: "high",
      risk_level: "high",
      rainfall_mm: 20,
      discharge_m3_s: 400,
    }),
    score({
      township_id: "t3",
      township_name: "Taungoo",
      district_id: "d1",
      lead_days: 0,
      flood_probability: 0.1,
      risk_level: "low",
      rainfall_mm: 5,
      discharge_m3_s: 100,
    }),
  ],
};

const plan = {
  plan_id: "p1",
  planning_date: "2026-10-31",
  status: "draft",
  warehouse: { id: "east", name: "Bago East", region: "east", latitude: 17.33, longitude: 96.48 },
  warehouses: [],
  totals: { affected_population: 8500, available_stock_units: 100, resources_needed_units: 200 },
  rows: [
    {
      township_id: "t2",
      township_name: "Pyay",
      latitude: 18.82,
      longitude: 95.22,
      population: 500,
      priority: "high",
      resources_label: "",
      quantities_label: "",
      line_items: [],
      route_id: "r2",
      depot_region: "west",
      has_shortage: false,
      requested_total: 50,
      allocated_total: 50,
    },
    {
      township_id: "t1",
      township_name: "Bago",
      latitude: 17.33,
      longitude: 96.48,
      population: 1000,
      priority: "severe",
      resources_label: "",
      quantities_label: "",
      line_items: [],
      route_id: "r1",
      depot_region: "east",
      has_shortage: true,
      requested_total: 100,
      allocated_total: 40,
    },
  ],
  shortages: [
    {
      category_code: "foods",
      item_code: "rice",
      name: "Rice",
      unit: "kg",
      requested: 100,
      available: 0,
      unmet: 100,
      depot_region: "east",
    },
  ],
  routes: [],
  model_version: "test",
  disclaimer: "Academic planning aid.",
} as AllocationPlanResponse;

const eastStock: InventorySnapshot = {
  region: "east",
  location: "Bago East",
  classes: [
    {
      code: "foods",
      name: "Food",
      entry_mode: "scan_or_manual",
      quantity: 4000,
      items: [
        { code: "rice", name: "Rice", quantity: 0, unit: "kg", capacity: 5000 },
        { code: "water", name: "Clean Water", quantity: 4000, unit: "L", capacity: 5000 },
      ],
    },
  ],
  movements: [],
};

const westStock: InventorySnapshot = {
  region: "west",
  location: "Bago West",
  classes: [
    {
      code: "utilities",
      name: "Utilities",
      entry_mode: "scan_or_manual",
      quantity: 1000,
      items: [{ code: "jackets", name: "Life Jackets", quantity: 1000, unit: "pcs", capacity: 5000 }],
    },
  ],
  movements: [],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("HomeDashboard", () => {
  it("summarizes flood risk, the latest plan, and depot stock", async () => {
    vi.mocked(api.predictionRegionForecast).mockResolvedValue(forecast);
    vi.mocked(api.allocationPlans).mockResolvedValue([
      {
        plan_id: "old",
        status: "confirmed",
        created_at: "2026-10-01T00:00:00Z",
        prediction_run_id: null,
        planning_date: "2026-10-01",
      },
      {
        plan_id: "p1",
        status: "draft",
        created_at: "2026-10-30T12:00:00Z",
        prediction_run_id: 1,
        planning_date: "2026-10-31",
      },
    ]);
    vi.mocked(api.allocationPlanDetail).mockResolvedValue(plan);
    vi.mocked(api.inventoryLocations).mockResolvedValue({ locations: [eastStock, westStock] });
    const onOpenPage = vi.fn();
    const onPlanResources = vi.fn();

    render(
      <HomeDashboard
        areas={{ state: "ready", data: areas }}
        onOpenPage={onOpenPage}
        onPlanResources={onPlanResources}
      />,
    );

    const overview = screen.getByRole("region", { name: "Overview" });
    expect(await within(overview).findByText("Severe")).toBeInTheDocument();
    expect(within(overview).getByText("High or severe in 2 districts")).toBeInTheDocument();
    expect(within(overview).getByText("5–80 mm")).toBeInTheDocument();
    expect(within(overview).getByText("1,200 m³/s")).toBeInTheDocument();
    expect(within(overview).getByText("Bago")).toBeInTheDocument();
    expect(await within(overview).findByText("8,500")).toBeInTheDocument();
    expect(within(overview).getByText("Latest plan · 2026-10-31")).toBeInTheDocument();

    expect(await screen.findByText("Draft · 2026-10-31 · 1 unmet line")).toBeInTheDocument();
    expect(screen.getByText("40 allocated of 100 requested")).toBeInTheDocument();
    expect(screen.getByText("50 allocated of 50 requested")).toBeInTheDocument();
    expect(screen.getByText("Rainfall · Bago: day 0 40 mm, day 1 80 mm")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Forecast rainfall sparkline" })).toBeInTheDocument();

    const counts = screen.getByRole("group", { name: "Stock counts" });
    expect(within(counts).getByText("3")).toBeInTheDocument();
    expect(within(counts).getByText("Items")).toBeInTheDocument();
    expect(within(counts).getAllByText("1")).toHaveLength(3);
    expect(screen.getByText("Consider restocking Rice (Bago East) and Life Jackets (Bago West).")).toBeInTheDocument();
    expect(screen.getByText("0 kg · Bago East")).toBeInTheDocument();

    expect(api.allocationPlanDetail).toHaveBeenCalledWith("p1");
    expect(api.allocationPlanDetail).not.toHaveBeenCalledWith("old");

    fireEvent.click(screen.getAllByRole("button", { name: "Plan resources" })[0]);
    expect(onPlanResources).toHaveBeenCalledWith(
      expect.objectContaining({
        townshipId: "t1",
        townshipName: "Bago",
        date: "2026-10-31",
        riskLevel: "severe",
        latitude: 17.33,
        longitude: 96.48,
        floodProbability: 0.82,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Open flood prediction" }));
    fireEvent.click(screen.getByRole("button", { name: "Open resource allocation" }));
    fireEvent.click(screen.getByRole("button", { name: "Open inventory" }));
    expect(onOpenPage).toHaveBeenNthCalledWith(1, "prediction");
    expect(onOpenPage).toHaveBeenNthCalledWith(2, "allocation");
    expect(onOpenPage).toHaveBeenNthCalledWith(3, "inventory");
  });

  it("keeps allocation and inventory when the flood forecast fails and no plan exists", async () => {
    vi.mocked(api.predictionRegionForecast).mockRejectedValue(new Error("forecast down"));
    vi.mocked(api.allocationPlans).mockResolvedValue([]);
    vi.mocked(api.inventoryLocations).mockResolvedValue({ locations: [eastStock] });
    const onOpenPage = vi.fn();

    render(
      <HomeDashboard
        areas={{ state: "ready", data: areas }}
        onOpenPage={onOpenPage}
        onPlanResources={vi.fn()}
      />,
    );

    expect(await screen.findByText("Flood forecast could not be loaded. forecast down")).toBeInTheDocument();
    expect(screen.getAllByText("Forecast unavailable").length).toBeGreaterThan(0);
    expect(await screen.findByText("No allocation plan yet. Create one from Resource Allocation.")).toBeInTheDocument();
    expect(await screen.findByText("Consider restocking Rice (Bago East).")).toBeInTheDocument();
    expect(screen.getByText("0 kg · Bago East")).toBeInTheDocument();
    expect(screen.queryByText("1,200 m³/s")).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Open resource allocation" })[0]);
    expect(onOpenPage).toHaveBeenCalledWith("allocation");
  });
});
