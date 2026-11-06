import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import HomeDashboard from "./HomeDashboard";
import { localToday } from "./lib/dates";
import type { AllocationPlanResponse, BagoAreasResponse, InventorySnapshot } from "./types";

vi.mock("react-leaflet", () => ({
  MapContainer: ({
    children,
    "aria-label": ariaLabel,
  }: {
    children: React.ReactNode;
    "aria-label"?: string;
  }) => (
    <div data-testid="map" aria-label={ariaLabel}>
      {children}
    </div>
  ),
  TileLayer: () => null,
  CircleMarker: () => null,
  Polyline: () => null,
  Popup: () => null,
  Tooltip: () => null,
  Pane: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  useMap: () => ({
    fitBounds: () => undefined,
    setView: () => undefined,
    invalidateSize: () => undefined,
    getSize: () => ({ x: 800, y: 600 }),
    getContainer: () => document.createElement("div"),
  }),
}));

vi.mock("./api", () => ({
  api: {
    predictionTimeline: vi.fn(),
    predictionCalendarBounds: vi.fn(),
    predictionMapScores: vi.fn(),
    allocationPlans: vi.fn(),
    allocationPlanDetail: vi.fn(),
    inventoryLocations: vi.fn(),
    allocationNetworkRoutes: vi.fn(),
    allocationStores: vi.fn().mockResolvedValue([]),
    floodCasesHighSevere: vi.fn().mockResolvedValue({
      counts: { total: 0, severe: 0, high: 0, recorded: 0, model: 0 },
      by_year: [],
      disclaimer: "",
      events: [],
    }),
  },
}));

const today = localToday();

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

function mockPredictionPanelApis(severeToday = true) {
  vi.mocked(api.predictionCalendarBounds).mockResolvedValue({
    history_start: "2010-01-01",
    operational_start: "2010-01-01",
    labeled_start: "2021-04-01",
    history_end: today,
    forecast_end: today,
    select_max: today,
  });
  vi.mocked(api.predictionMapScores).mockResolvedValue({
    date: today,
    model_version: "test",
    cached: false,
    scores: [],
  });
  vi.mocked(api.predictionTimeline).mockResolvedValue({
    township_id: "t1",
    as_of: today,
    timezone: "Asia/Yangon",
    model_version: "test",
    in_training_set: true,
    generated_at: "2026-10-10T00:00:00Z",
    potentially_exposed_population: 1000,
    disclaimer: "Test",
    days: [
      {
        date: today,
        period_type: "current",
        flood_probability: severeToday ? 0.82 : 0.12,
        predicted_flood: severeToday,
        probability_risk_level: severeToday ? "severe" : "low",
        risk_level: severeToday ? "severe" : "low",
        hydrology_risk_score: 20,
        hydrology_risk_level: severeToday ? "severe" : "low",
        rainfall_mm: 6.5,
        discharge_m3_s: 0.1,
        temperature_c: 28.3,
        relative_humidity_pct: 84,
        wind_speed_m_s: 1.6,
        rainfall_7d_mm: 29.4,
        impact_level: "unknown",
        potentially_exposed_population: 1000,
        potentially_affected_population: null,
        observed_flood: null,
        recorded_affected_people: null,
        data_status: "model_estimate",
        evidence_type: "model_prediction",
        probability_status: "uncalibrated_academic_score",
        forecast_horizon_hours: 0,
        input_freshness: {},
        uncertainty: "",
        key_factors: [],
      },
    ],
  });
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("HomeDashboard", () => {
  it("summarizes flood risk, the latest plan, and depot stock", async () => {
    mockPredictionPanelApis(true);
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
    vi.mocked(api.allocationNetworkRoutes).mockResolvedValue({
      routes: [],
      disclaimer: "Test",
    });
    const onOpenPage = vi.fn();
    const onPlanResources = vi.fn();

    render(
      <HomeDashboard
        areas={{ state: "ready", data: areas }}
        onOpenPage={onOpenPage}
        onPlanResources={onPlanResources}
      />,
    );

    expect(screen.queryByRole("region", { name: "Overview" })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Flood Prediction" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Resource Allocation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Inventory Management" })).toBeInTheDocument();

    expect(await screen.findByRole("heading", { name: "Route map" })).toBeInTheDocument();
    expect(screen.getByLabelText("Route map context")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Route map context")).getByText(today)).toBeInTheDocument();
    expect(within(screen.getByLabelText("Route map context")).getByText("All high and severe")).toBeInTheDocument();
    expect(screen.getByTestId("map")).toBeInTheDocument();
    expect(screen.getByLabelText("Map legend")).toBeInTheDocument();
    expect(screen.getByText("East depot routes")).toBeInTheDocument();
    expect(screen.queryByText(/high or severe$/)).not.toBeInTheDocument();

    expect(await screen.findByLabelText("Selected date")).toBeInTheDocument();
    expect(screen.getByLabelText("Selected date")).toHaveValue(today);
    expect(screen.getByLabelText("Selected township")).toBeInTheDocument();
    expect(await screen.findByText("Flood chance")).toBeInTheDocument();
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Forecast rainfall sparkline" })).not.toBeInTheDocument();

    expect(screen.getByRole("group", { name: "Inventory depot" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Both depots" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/Showing inventory for/i)).toHaveTextContent("Bago East & Bago West");

    const totals = await screen.findByLabelText("Inventory totals");
    expect(within(totals).getByText("Total items")).toBeInTheDocument();
    expect(within(totals).getByText("5,000")).toBeInTheDocument();
    expect(within(totals).getByText("Food")).toBeInTheDocument();
    expect(within(totals).getByText("4,000")).toBeInTheDocument();
    expect(within(totals).getByText("Utilities")).toBeInTheDocument();
    expect(within(totals).getByText("1,000")).toBeInTheDocument();
    const inventoryItems = await screen.findByLabelText("Inventory items");
    expect(within(inventoryItems).getByText("Rice")).toBeInTheDocument();
    expect(within(inventoryItems).getByText("Clean Water")).toBeInTheDocument();
    expect(within(inventoryItems).getByText("Life Jackets")).toBeInTheDocument();
    expect(within(inventoryItems).getByText("0 kg · Bago East")).toBeInTheDocument();
    expect(within(inventoryItems).getByText("4,000 L · Bago East")).toBeInTheDocument();
    expect(within(inventoryItems).getByText("1,000 pcs · Bago West")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Bago East" }));
    expect(screen.getByRole("button", { name: "Bago East" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/Showing inventory for/i)).toHaveTextContent("Bago East");
    expect(within(await screen.findByLabelText("Inventory items")).queryByText("Life Jackets")).not.toBeInTheDocument();
    expect(within(screen.getByLabelText("Inventory items")).getByText("Rice")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Both depots" }));
    expect(within(screen.getByLabelText("Inventory items")).getByText("Life Jackets")).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: "View stock" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Consider restocking/i)).not.toBeInTheDocument();

    expect(api.allocationPlanDetail).toHaveBeenCalledWith("p1");
    expect(api.allocationPlanDetail).not.toHaveBeenCalledWith("old");

    fireEvent.click(screen.getByRole("button", { name: "Plan resource allocation" }));
    expect(onPlanResources).toHaveBeenCalledWith(
      expect.objectContaining({
        townshipId: "t1",
        townshipName: "Bago",
        date: today,
        riskLevel: "severe",
        latitude: 17.33,
        longitude: 96.48,
        floodProbability: 0.82,
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Prediction details" }));
    fireEvent.click(screen.getByRole("button", { name: "Open flood prediction" }));
    fireEvent.click(screen.getByRole("button", { name: "Open resource allocation" }));
    fireEvent.click(screen.getByRole("button", { name: "Open inventory" }));
    expect(onOpenPage).toHaveBeenNthCalledWith(1, "prediction");
    expect(onOpenPage).toHaveBeenNthCalledWith(2, "prediction");
    expect(onOpenPage).toHaveBeenNthCalledWith(3, "allocation");
    expect(onOpenPage).toHaveBeenNthCalledWith(4, "inventory");
  });

  it("keeps allocation and inventory when the flood forecast fails and no plan exists", async () => {
    mockPredictionPanelApis(false);
    vi.mocked(api.allocationPlans).mockResolvedValue([]);
    vi.mocked(api.inventoryLocations).mockResolvedValue({ locations: [eastStock] });
    vi.mocked(api.allocationNetworkRoutes).mockResolvedValue({
      routes: [],
      disclaimer: "Test",
    });
    const onOpenPage = vi.fn();

    render(
      <HomeDashboard
        areas={{ state: "ready", data: areas }}
        onOpenPage={onOpenPage}
        onPlanResources={vi.fn()}
      />,
    );

    expect(await screen.findByText("No allocation needed.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Overview" })).not.toBeInTheDocument();
    expect(screen.queryByText("Flood forecast could not be loaded. forecast down")).not.toBeInTheDocument();
    expect(await screen.findByText("No allocation plan yet. Create one from Resource Allocation.")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Route map" })).toBeInTheDocument();
    expect(screen.getByTestId("map")).toBeInTheDocument();
    const inventoryItems = await screen.findByLabelText("Inventory items");
    expect(within(inventoryItems).getByText("Rice")).toBeInTheDocument();
    expect(within(inventoryItems).getByText("Clean Water")).toBeInTheDocument();
    expect(within(inventoryItems).getByText("0 kg · Bago East")).toBeInTheDocument();
    expect(screen.queryByText(/Consider restocking/i)).not.toBeInTheDocument();
    expect(screen.queryByText("1,200 m³/s")).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Open resource allocation" })[0]);
    expect(onOpenPage).toHaveBeenCalledWith("allocation");
  });
});
