import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  CircleMarker: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Popup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Polyline: () => null,
  Tooltip: () => null,
  GeoJSON: () => <div data-testid="geojson" />,
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
    health: vi.fn().mockResolvedValue({
      status: "ok",
      service: "hydroflow-api",
      version: "0.2.0",
      database: { ready: true, missing_tables: [], revision: "20261015_0001" },
      models: { flood: true, help: true, allocation: true },
    }),
    runs: vi.fn().mockResolvedValue([]),
    inundationProducts: vi.fn().mockResolvedValue([]),
    settlements: vi.fn().mockResolvedValue([]),
    allocationPlan: vi.fn().mockResolvedValue({
      plan_id: "p1",
      planning_date: "2026-10-19",
      warehouse: { id: "depot-bago", name: "Bago depot (east)", region: "east", latitude: 17.335, longitude: 96.481 },
      warehouses: [
        { id: "depot-bago", name: "Bago depot (east)", region: "east", latitude: 17.335, longitude: 96.481 },
        { id: "depot-pyay", name: "Pyay depot (west)", region: "west", latitude: 18.817, longitude: 95.217 },
      ],
      totals: { affected_population: 8500, available_stock_units: 1200, resources_needed_units: 900 },
      rows: [],
      shortages: [],
      routes: [],
      model_version: "flood-help-v2",
      disclaimer: "Academic planning aid.",
    }),
    inventory: vi.fn().mockImplementation(async (region: string) => ({
      region,
      location: region === "east" ? "Bago East" : "Bago West",
      classes: [],
      movements: [],
    })),
    inventoryLocations: vi.fn().mockResolvedValue({ locations: [] }),
    allocationPlans: vi.fn().mockResolvedValue([]),
    allocationNetworkRoutes: vi.fn().mockResolvedValue({ routes: [], disclaimer: "test" }),
    allocationPlanDetail: vi.fn(),
    predictionRegionForecast: vi.fn().mockResolvedValue({
      as_of: "2026-10-31",
      run_id: null,
      model_version: "test",
      feature_version: "v2",
      disclaimer: "Test",
      cached: true,
      labels_found: false,
      label_file: null,
      missing_inputs: [],
      scores: [],
    }),
    predictionCalendarBounds: vi.fn().mockResolvedValue({
      history_start: "2010-01-01",
      operational_start: "2010-01-01",
      labeled_start: "2021-04-01",
      history_end: "2026-10-20",
      forecast_end: "2026-10-27",
      select_max: "2026-10-27",
    }),
    predictionHazardSurface: vi.fn().mockResolvedValue({
      township_id: "MMR007001701",
      status: "ready",
      jrc_depth_100y_max_m: 1.0,
      hand_pct_lt_2m: 10.0,
    }),
    predictionTimeline: vi.fn().mockResolvedValue({
      township_id: "MMR007001701",
      as_of: "2026-10-19",
      timezone: "Asia/Yangon",
      model_version: "test",
      in_training_set: true,
      generated_at: "2026-10-19T00:00:00Z",
      potentially_exposed_population: 1000,
      disclaimer: "Test",
      days: [
        {
          date: "2026-10-18",
          period_type: "historical",
          flood_probability: 0.1,
          predicted_flood: false,
          probability_risk_level: "low",
          risk_level: "low",
          rainfall_mm: 7.1,
          discharge_m3_s: 0.2,
          relative_humidity_pct: 80,
          impact_level: "unknown",
          data_status: "model_estimate",
          evidence_type: "model_prediction",
          key_factors: [],
          input_freshness: {},
          uncertainty: "",
          forecast_horizon_hours: 0,
        },
        {
          date: "2026-10-19",
          period_type: "current",
          flood_probability: 0,
          predicted_flood: false,
          probability_risk_level: "low",
          risk_level: "low",
          rainfall_mm: 0.9,
          discharge_m3_s: 0.2,
          relative_humidity_pct: 88,
          impact_level: "unknown",
          data_status: "model_estimate",
          evidence_type: "model_prediction",
          key_factors: [],
          input_freshness: {},
          uncertainty: "",
          forecast_horizon_hours: 0,
        },
        {
          date: "2026-10-20",
          period_type: "forecast",
          flood_probability: 0.55,
          predicted_flood: true,
          probability_risk_level: "high",
          risk_level: "high",
          rainfall_mm: 30,
          discharge_m3_s: 70,
          impact_level: "unknown",
          data_status: "model_estimate",
          evidence_type: "model_prediction",
          key_factors: [],
          input_freshness: {},
          uncertainty: "",
          forecast_horizon_hours: 24,
        },
      ],
    }),
    predictionMapScores: vi.fn().mockResolvedValue({
      date: "2026-10-19",
      model_version: "test",
      cached: false,
      scores: [],
    }),
    forecast: vi.fn().mockResolvedValue({ latitude: 17.336, longitude: 96.481, points: [] }),
    alerts: vi.fn().mockResolvedValue([]),
    topography: vi.fn().mockResolvedValue({
      latitude: 17.3358,
      longitude: 96.4839,
      elevation_m: 18.4,
      dataset: "COP30",
      vertical_datum: "EGM2008",
      vertical_datum_epsg: "3855",
      unit: "Meters",
      source: "OpenTopography Copernicus GLO-30",
      note: "Surface elevation at the requested point. The flood model does not use this value.",
    }),
    historical: vi.fn().mockResolvedValue({
      latitude: 17.336,
      longitude: 96.481,
      points: [
        {
          date: "2026-01-01",
          precipitation_mm: 4,
          temperature_c: 23.5,
          relative_humidity_pct: 80,
        },
      ],
    }),
    floodCasesHighSevere: vi.fn().mockResolvedValue({
      counts: { total: 0, severe: 0, high: 0, recorded: 0, model: 0 },
      by_year: [],
      disclaimer: "",
      events: [],
    }),
    floodHistory: vi.fn().mockResolvedValue({
      source: "Bago relief records",
      disclaimer: "Recorded impacts, not model predictions.",
      matched_records: 1,
      records: [
        {
          date: "2025-10-02",
          township_id: "pyay",
          township: "Pyay",
          latitude: 18.817,
          longitude: 95.217,
          households: 22,
          affected_people: 72,
          impact_severity: "low",
        },
      ],
    }),
    townships: vi.fn().mockResolvedValue([
      { township_id: "bago", township: "Bago", latitude: 17.335, longitude: 96.481 },
    ]),
    bagoAreas: vi.fn().mockResolvedValue({
      source: "OCHA Myanmar COD-AB v01",
      dataset_version: "COD-AB-v01-2024-02-15",
      license: "CC BY 3.0 IGO",
      coverage_note: "Admin 4 and 5 coverage is partial.",
      region_id: "MMR007",
      region_name_en: "Bago",
      region_name_local: "ပဲခူးတိုင်းဒေသကြီး",
      latitude: 18.2638,
      longitude: 96.0673,
      districts: [
        {
          id: "MMR007D001",
          slug: "bago-MMR007D001",
          name_en: "Bago",
          name_local: "ပဲခူးခရိုင်",
          latitude: 17.6768,
          longitude: 96.6216,
          level: 2,
          area_type: "district",
          coverage_status: "complete",
          townships: [
            {
              id: "MMR007001701",
              slug: "bago-MMR007001701",
              name_en: "Bago",
              name_local: "ပဲခူး",
              latitude: 17.3358,
              longitude: 96.4839,
              level: 3,
              area_type: "township",
              coverage_status: "complete",
            },
          ],
        },
        {
          id: "MMR008D001",
          slug: "pyay-MMR008D001",
          name_en: "Pyay",
          name_local: "ပြည်ခရိုင်",
          latitude: 18.696,
          longitude: 95.3295,
          level: 2,
          area_type: "district",
          coverage_status: "complete",
          townships: [
            {
              id: "MMR008001",
              slug: "pyay-MMR008001",
              name_en: "Pyay",
              name_local: "ပြည်",
              latitude: 18.817,
              longitude: 95.217,
              level: 3,
              area_type: "township",
              coverage_status: "complete",
            },
          ],
        },
      ],
    }),
    outlook: vi.fn().mockResolvedValue({
      township_id: "MMR007001701",
      source: "joined forecast",
      model_version: "hist_gradient_boosting",
      in_training_set: true,
      days: [
        {
          date: new Date(Date.now() - new Date().getTimezoneOffset() * 60_000).toISOString().slice(0, 10),
          precipitation_mm: 12,
          discharge_m3_s: 40,
          temperature_c: 28,
          relative_humidity_pct: 71,
          flood_probability: 0.21,
          predicted_flood: false,
          risk_score: 0.3,
          risk_level: "low",
          alert_recorded: false,
          forecast_horizon_hours: 0,
          evidence_type: "model_prediction",
          probability_status: "uncalibrated_academic_score",
          input_freshness: {},
          uncertainty: "",
        },
      ],
    }),
    sources: vi.fn().mockResolvedValue([]),
    officialWarnings: vi.fn().mockResolvedValue([]),
    riskResults: vi.fn().mockResolvedValue([]),
    adminAreas: vi.fn().mockResolvedValue({
      source: "OCHA Myanmar COD-AB v01",
      dataset_version: "COD-AB-v01-2024-02-15",
      license: "CC BY 3.0 IGO",
      coverage_note: "Admin 4 and 5 coverage is partial.",
      areas: [],
    }),
    runPrediction: vi.fn(),
    census: vi.fn().mockResolvedValue({
      source: "2024 Population and Housing Census, Bago Region tables",
      source_file: "data/2024_census_bago_report (update).xlsx",
      census_year: 2024,
      region_name_en: "Bago",
      region_name_local: "ပဲခူးတိုင်းဒေသကြီး",
      notes: ["Age groups are not published for individual townships."],
      dwelling_types: [{ key: "wooden", name_local: "သစ်သားအိမ်", name_en: "Wooden house" }],
      population: {
        total: { total: 4453687, male: 2078567, female: 2375120 },
        urban: { total: 1128732, male: 512226, female: 616506 },
        rural: { total: 3324955, male: 1566341, female: 1758614 },
      },
      age_groups: [],
      households: {
        total: 1029962,
        by_size: [{ size: "4", households: 231119 }],
        by_dwelling: {
          total: 1029962,
          apartment: 0,
          brick: 0,
          semi_brick: 0,
          wooden: 1029962,
          bamboo: 0,
          hut: 0,
          other: 0,
        },
        urban_dwellings: {
          total: 266225,
          apartment: 0,
          brick: 0,
          semi_brick: 0,
          wooden: 266225,
          bamboo: 0,
          hut: 0,
          other: 0,
        },
        rural_dwellings: {
          total: 763737,
          apartment: 0,
          brick: 0,
          semi_brick: 0,
          wooden: 763737,
          bamboo: 0,
          hut: 0,
          other: 0,
        },
      },
      districts: [
        {
          name_en: "Bago",
          name_local: "ပဲခူးခရိုင်",
          population: { total: 927389, male: 429760, female: 497629 },
          age_groups: [
            {
              label: "0-4",
              min_age: 0,
              max_age: 4,
              total: { total: 64676, male: 32937, female: 31739 },
              urban: { total: 19338, male: 9780, female: 9558 },
              rural: { total: 45338, male: 23157, female: 22181 },
            },
          ],
          households: {
            total: 224609,
            by_size: [],
            by_dwelling: {
              total: 224609,
              apartment: 0,
              brick: 0,
              semi_brick: 0,
              wooden: 224609,
              bamboo: 0,
              hut: 0,
              other: 0,
            },
          },
          townships: [
            {
              name_en: "Bago",
              name_local: "ပဲခူးမြို့နယ်",
              population: { total: 484994, male: 224660, female: 260334 },
              households: {
                total: 111465,
                by_size: [{ size: "4", households: 25426 }],
                by_dwelling: {
                  total: 111465,
                  apartment: 0,
                  brick: 0,
                  semi_brick: 0,
                  wooden: 48806,
                  bamboo: 0,
                  hut: 0,
                  other: 0,
                },
              },
            },
          ],
        },
      ],
    }),
    helpBrief: vi.fn().mockResolvedValue({
      source: "Bago relief records",
      disclaimer: "Recorded impacts, not flood-help model predictions.",
      recorded_flood_days: 12,
      recorded_households: 40,
      recorded_affected_people: 90,
      townships_with_impact: 3,
      highest_impacts: [
        {
          date: "2024-09-12",
          township_id: "bago",
          township: "Bago",
          latitude: 17.336,
          longitude: 96.481,
          households: 40,
          affected_people: 90,
          impact_severity: "moderate",
        },
      ],
    }),
    help: vi.fn().mockResolvedValue({
      township_id: "bago",
      source: "Open-Meteo rainfall and GloFAS discharge",
      model_version: "flood-help-v2",
      disclaimer: "Academic planning aid. Not an operational humanitarian response plan.",
      days: [
        {
          date: "2026-10-01",
          help_probability: 0.42,
          predicted_help: true,
          expected_affected_people: 4,
          expected_households: 2,
          assistance_priority: "low",
          shelter_kits: 2,
          food_rations_3d: 12,
          drinking_water_liters_3d: 180,
        },
      ],
    }),
  },
}));

afterEach(() => {
  cleanup();
});

describe("dashboard", () => {
  it("renders the HydroFlow shell and opens flood prediction", async () => {
    render(<App />);

    expect(await screen.findByText("API ok", {}, { timeout: 8000 })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Home" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Home" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Flood Prediction" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resource Allocation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Inventory Management" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dashboard" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Flood Prediction" }));
    expect(await screen.findByRole("heading", { name: "Districts" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Flood Prediction" })).toBeInTheDocument();
    expect(screen.getByTestId("map")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next 7 days" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous 7 days" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Flood prediction" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close sidebar" }));
    expect(screen.getByRole("button", { name: "Open sidebar" })).toBeInTheDocument();
  }, 20000);

  it("opens inventory and resource allocation", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Inventory Management" }));
    expect(await screen.findByRole("heading", { name: "Inventory Management" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "+ Add Item" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Resource Allocation" }));
    expect(await screen.findByRole("heading", { name: "Route map" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "In stock" })).not.toBeInTheDocument();
    expect(screen.getByText(/create a plan for high and severe deliveries/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create plan" })).toBeInTheDocument();
    expect(screen.getAllByText("High and severe only").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByRole("combobox")).toHaveLength(1);
    expect(screen.getByRole("combobox", { name: "Region" })).toBeInTheDocument();
  }, 30000);
});
