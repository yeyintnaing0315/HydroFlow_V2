import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import FloodPredictionDashboard from "./FloodPredictionDashboard";
import { BASEMAP_ATTRIBUTION, BASEMAP_TILE_URL } from "./components/map/BasemapTileLayer";
import { riskLabel } from "./components/prediction/mapUtils";
const { calendarSelectMax } = vi.hoisted(() => {
  const day = new Date();
  const calendarSelectMax = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
  return { calendarSelectMax };
});

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: ({ url, attribution }: { url?: string; attribution?: string }) => (
    <div data-testid="basemap" data-url={url} data-attribution={attribution} />
  ),
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
    predictionTimeline: vi.fn().mockResolvedValue({
      township_id: "MMR007001701",
      as_of: "2026-10-19",
      timezone: "Asia/Yangon",
      model_version: "test",
      in_training_set: true,
      generated_at: "2026-10-10T00:00:00Z",
      potentially_exposed_population: 1000,
      disclaimer: "Test",
      days: [
        {
          date: "2026-10-18",
          period_type: "historical",
          flood_probability: 0.35,
          predicted_flood: false,
          probability_risk_level: "moderate",
          risk_level: "moderate",
          hydrology_risk_score: 40,
          hydrology_risk_level: "moderate",
          rainfall_mm: 20,
          discharge_m3_s: 50,
          impact_level: "unknown",
          potentially_exposed_population: 1000,
          potentially_affected_population: null,
          observed_flood: false,
          recorded_affected_people: null,
          data_status: "model_estimate",
          evidence_type: "model_prediction",
          probability_status: "uncalibrated_academic_score",
          forecast_horizon_hours: 0,
          input_freshness: {},
          uncertainty: "",
          key_factors: [],
        },
        {
          date: "2026-10-19",
          period_type: "current",
          flood_probability: 0.21,
          predicted_flood: false,
          probability_risk_level: "low",
          risk_level: "low",
          hydrology_risk_score: 20,
          hydrology_risk_level: "low",
          rainfall_mm: 10,
          discharge_m3_s: 30,
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
        {
          date: "2026-10-20",
          period_type: "forecast",
          flood_probability: 0.55,
          predicted_flood: true,
          probability_risk_level: "high",
          risk_level: "high",
          hydrology_risk_score: 60,
          hydrology_risk_level: "high",
          rainfall_mm: 30,
          discharge_m3_s: 70,
          temperature_c: 31.2,
          relative_humidity_pct: 71,
          wind_speed_m_s: 3.5,
          rainfall_7d_mm: 118.4,
          impact_level: "unknown",
          potentially_exposed_population: 1000,
          potentially_affected_population: null,
          observed_flood: null,
          recorded_affected_people: null,
          data_status: "model_estimate",
          evidence_type: "model_prediction",
          probability_status: "uncalibrated_academic_score",
          forecast_horizon_hours: 24,
          input_freshness: {},
          uncertainty: "",
          key_factors: [],
        },
      ],
    }),
    predictionCalendarBounds: vi.fn().mockResolvedValue({
      history_start: "2010-01-01",
      operational_start: "2010-01-01",
      labeled_start: "2021-04-01",
      history_end: "2026-10-20",
      forecast_end: calendarSelectMax,
      select_max: calendarSelectMax,
    }),
    predictionHazardSurface: vi.fn().mockResolvedValue({
      township_id: "bago",
      status: "ready",
      jrc_depth_100y_max_m: 1.2,
      jrc_pct_inundated_100y: 12.0,
      hand_pct_lt_2m: 18.0,
      worldcover_pct_built_floodplain: 4.0,
    }),
    predictionMapScores: vi.fn().mockResolvedValue({
      date: "2026-10-10",
      model_version: "test",
      cached: false,
      scores: [],
    }),
  },
}));

const areas = {
  state: "ready" as const,
  data: {
    source: "test",
    dataset_version: "v1",
    license: "test",
    coverage_note: "",
    region_id: "MMR007",
    region_name_en: "Bago",
    region_name_local: "Bago",
    latitude: 18,
    longitude: 96,
    districts: [
      {
        id: "MMR007D001",
        slug: "bago",
        name_en: "Bago",
        name_local: "Bago",
        latitude: 17.6,
        longitude: 96.6,
        level: 2,
        area_type: "district",
        coverage_status: "complete",
        townships: [
          {
            id: "MMR007001701",
            slug: "bago-township",
            name_en: "Bago",
            name_local: "Bago",
            latitude: 17.3358,
            longitude: 96.4839,
            level: 3,
            area_type: "township",
            coverage_status: "complete",
          },
          {
            id: "MMR007001702",
            slug: "daik-u",
            name_en: "Daik-U",
            name_local: "Daik-U",
            latitude: 17.5,
            longitude: 96.5,
            level: 3,
            area_type: "township",
            coverage_status: "complete",
          },
        ],
      },
      {
        id: "MMR007D004",
        slug: "taungoo",
        name_en: "Taungoo",
        name_local: "Taungoo",
        latitude: 18.9,
        longitude: 96.4,
        level: 2,
        area_type: "district",
        coverage_status: "complete",
        townships: [
          {
            id: "MMR007004701",
            slug: "taungoo-township",
            name_en: "Taungoo",
            name_local: "Taungoo",
            latitude: 18.9,
            longitude: 96.4,
            level: 3,
            area_type: "township",
            coverage_status: "complete",
          },
          {
            id: "MMR007004702",
            slug: "htantabin",
            name_en: "Htantabin",
            name_local: "Htantabin",
            latitude: 18.8,
            longitude: 96.3,
            level: 3,
            area_type: "township",
            coverage_status: "complete",
          },
        ],
      },
    ],
  },
};

afterEach(() => {
  cleanup();
});

describe("FloodPredictionDashboard", () => {
  it("maps moderate risk to Medium label", () => {
    expect(riskLabel("moderate")).toBe("Medium");
  });

  it("shows the map, compact day metrics, and both day groups", async () => {
    render(
      <FloodPredictionDashboard
        areas={areas}
        health={{ state: "ready", data: { status: "ok", service: "x", version: "1", database: { ready: true, missing_tables: [] }, models: { flood: true, help: true, allocation: true } } }}
        runs={{ state: "empty" }}
        inundation={{ state: "empty" }}
        settlements={{ state: "empty" }}
      />,
    );
    expect(await screen.findByRole("heading", { name: "Flood prediction" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Bago districts" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next 7 days" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Previous 7 days" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByLabelText("Selected date")).toBeInTheDocument();
    expect(screen.getByTestId("map")).toBeInTheDocument();
    expect(screen.getByTestId("basemap")).toHaveAttribute("data-url", BASEMAP_TILE_URL);
    expect(screen.getByTestId("basemap")).toHaveAttribute("data-attribution", BASEMAP_ATTRIBUTION);

    expect(screen.queryByRole("button", { name: /2026-10-18/ })).not.toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /2026-10-20/ }));

    const metrics = await screen.findByRole("table", { name: "Flood prediction" });
    expect(within(metrics).getByText("Flood chance")).toBeInTheDocument();
    expect(within(metrics).getByText("55%")).toBeInTheDocument();
    expect(within(metrics).getByText("Risk")).toBeInTheDocument();
    expect(within(metrics).getByText("High")).toBeInTheDocument();
    expect(within(metrics).getByText("Rainfall")).toBeInTheDocument();
    expect(within(metrics).getByText("30.0 mm")).toBeInTheDocument();
    expect(within(metrics).getByText("Discharge")).toBeInTheDocument();
    expect(within(metrics).getByText(/70\.0/)).toBeInTheDocument();
    expect(within(metrics).queryByText("Humidity")).not.toBeInTheDocument();
    expect(within(metrics).queryByText("Lead time")).not.toBeInTheDocument();
    const weather = screen.getByRole("table", { name: "Weather conditions" });
    expect(within(weather).getByText("Temperature")).toBeInTheDocument();
    expect(within(weather).getByText("31.2 °C")).toBeInTheDocument();
    expect(within(weather).getByText("Humidity")).toBeInTheDocument();
    expect(within(weather).getByText("71%")).toBeInTheDocument();
    expect(within(weather).getByText("3.5 m/s")).toBeInTheDocument();
    expect(within(weather).getByText("118.4 mm")).toBeInTheDocument();
    expect(screen.queryByText("Heuristic risk")).not.toBeInTheDocument();
    expect(screen.queryByText("Flood in next 3 days")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Plan resource allocation" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Previous 7 days" }));
    fireEvent.click(await screen.findByRole("button", { name: /2026-10-18/ }));
    expect(await screen.findByText(/No allocation needed/i)).toBeInTheDocument();
  });

  it("scopes the township dropdown to the active district chip", async () => {
    const view = render(
      <FloodPredictionDashboard
        areas={areas}
        health={{ state: "ready", data: { status: "ok", service: "x", version: "1", database: { ready: true, missing_tables: [] }, models: { flood: true, help: true, allocation: true } } }}
        runs={{ state: "empty" }}
        inundation={{ state: "empty" }}
        settlements={{ state: "empty" }}
      />,
    );

    const townshipSelect = () => screen.getByRole("combobox", { name: "Selected township" });
    await waitFor(() => expect(townshipSelect()).toHaveValue("MMR007001701"));

    const districtChips = within(view.container).getByTestId("district-chips");
    fireEvent.click(within(districtChips).getByRole("button", { name: "Bago" }));
    await waitFor(() => expect(townshipSelect()).toHaveValue("MMR007001701"));
    expect(within(townshipSelect()).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Bago",
      "Daik-U",
    ]);

    fireEvent.click(within(districtChips).getByRole("button", { name: "Taungoo" }));
    await waitFor(() => expect(townshipSelect()).toHaveValue("MMR007004701"));
    expect(within(townshipSelect()).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Taungoo",
      "Htantabin",
    ]);

    fireEvent.change(townshipSelect(), { target: { value: "MMR007004702" } });
    expect(townshipSelect()).toHaveValue("MMR007004702");

    fireEvent.click(within(districtChips).getByRole("button", { name: "Bago" }));
    await waitFor(() => expect(townshipSelect()).toHaveValue("MMR007001701"));

    fireEvent.click(within(districtChips).getByRole("button", { name: "All districts" }));
    expect(within(townshipSelect()).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Bago",
      "Daik-U",
      "Taungoo",
      "Htantabin",
    ]);
  });
});
