import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ResourceAllocationDashboard from "./ResourceAllocationDashboard";
import { api } from "./api";

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  CircleMarker: () => null,
  Popup: () => null,
  Polyline: () => null,
  Tooltip: () => null,
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
    inventory: vi.fn().mockResolvedValue({ region: "east", location: "Bago East", classes: [], movements: [] }),
    census: vi.fn().mockResolvedValue({ districts: [] }),
    allocationPlan: vi.fn().mockResolvedValue({
      plan_id: "p1",
      planning_date: "2026-10-20",
      warehouse: { id: "depot-bago", name: "Bago depot (east)", region: "east", latitude: 17.335, longitude: 96.481 },
      warehouses: [],
      totals: { affected_population: 0, available_stock_units: 0, resources_needed_units: 0 },
      rows: [],
      shortages: [],
      routes: [],
      model_version: "test",
      disclaimer: "Academic allocation illustration. Not an operational dispatch plan.",
    }),
    allocationStores: vi.fn().mockResolvedValue([]),
    allocationPlans: vi.fn().mockResolvedValue([]),
    allocationPlanDetail: vi.fn(),
    compareTownshipRoutes: vi.fn().mockResolvedValue({
      plan_id: "p1",
      township_id: "bago",
      depot_region: "east",
      alternatives: [],
      alternatives_available: false,
      rainfall_mm: null,
      discharge_m3_s: null,
      flood_probability: null,
      risk_band: null,
    }),
    selectTownshipRoute: vi.fn(),
    predictionMapScores: vi.fn().mockResolvedValue({ date: "2026-10-20", model_version: "test", cached: false, scores: [] }),
    bagoAreas: vi.fn().mockResolvedValue({
      source: "test",
      dataset_version: "test",
      license: "test",
      coverage_note: "",
      region_id: "MMR007",
      region_name_en: "Bago",
      region_name_local: "Bago",
      latitude: 18.26,
      longitude: 96.07,
      districts: [],
    }),
    helpSummary: vi.fn(),
    allocationNetworkRoutes: vi.fn().mockResolvedValue({ routes: [], disclaimer: "test" }),
  },
}));

const samplePlan = {
  plan_id: "p1",
  planning_date: "2026-10-20",
  warehouse: { id: "depot-bago", name: "Bago depot (east)", region: "east" as const, latitude: 17.335, longitude: 96.481 },
  warehouses: [],
  totals: { affected_population: 30, available_stock_units: 100, resources_needed_units: 40 },
  shortages: [],
  routes: [],
  model_version: "test",
  disclaimer: "Academic allocation illustration. Not an operational dispatch plan.",
  rows: [
    {
      township_id: "bago",
      township_name: "Bago",
      latitude: 17.33,
      longitude: 96.48,
      population: 20,
      priority: "high" as const,
      resources_label: "Rice",
      quantities_label: "10 bag",
      route_id: "Route A",
      depot_region: "east" as const,
      has_shortage: false,
      line_items: [
        { category_code: "foods", item_code: "rice", name: "Rice", unit: "bag", requested: 20, allocated: 10 },
      ],
    },
    {
      township_id: "taungoo",
      township_name: "Taungoo",
      latitude: 18.93,
      longitude: 96.43,
      population: 10,
      priority: "severe" as const,
      resources_label: "Oil",
      quantities_label: "4 bottle",
      route_id: "Route A",
      depot_region: "east" as const,
      has_shortage: true,
      line_items: [
        { category_code: "foods", item_code: "oil", name: "Oil", unit: "bottle", requested: 10, allocated: 4 },
      ],
    },
  ],
};

afterEach(() => {
  cleanup();
});

describe("ResourceAllocationDashboard", () => {
  it("shows read-only high/severe scope and sends min_priority high", async () => {
    render(
      <ResourceAllocationDashboard startDate="2026-10-20" onStartDate={() => undefined} focus={null} />,
    );

    expect(screen.getByText("High and severe only")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "High and severe townships" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Township" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Affected people" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Allocation plan" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "East and west stock" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Bago (east)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Pyay (west)" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Township allocations" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Inventory unavailable/)).not.toBeInTheDocument();
    expect(api.census).not.toHaveBeenCalled();
    await waitFor(() => expect(api.inventory).toHaveBeenCalledWith("east"));
    expect(api.inventory).toHaveBeenCalledWith("west");
    expect(api.helpSummary).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Create plan" }));

    await waitFor(() => expect(api.allocationPlan).toHaveBeenCalled());
    expect(api.allocationPlan).toHaveBeenCalledWith(
      expect.objectContaining({ min_priority: "high", include_all_high_severe: true }),
    );
  });

  it("shows focus risk when opened from flood prediction", async () => {
    render(
      <ResourceAllocationDashboard
        startDate="2026-10-20"
        onStartDate={() => undefined}
        focus={{
          townshipId: "MMR007001701",
          townshipName: "Bago",
          date: "2026-10-20",
          riskLevel: "high",
          latitude: 17.33,
          longitude: 96.48,
        }}
      />,
    );

    expect(screen.getByText("High risk")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Create plan" }));
    await waitFor(() => expect(api.allocationPlan).toHaveBeenCalled());
    expect(api.allocationPlan).toHaveBeenCalledWith(
      expect.objectContaining({
        min_priority: "high",
        include_all_high_severe: false,
        township_ids: ["MMR007001701"],
      }),
    );
  });

  it("shows line items for the selected township", async () => {
    vi.mocked(api.allocationPlan).mockResolvedValueOnce(samplePlan);
    render(
      <ResourceAllocationDashboard startDate="2026-10-20" onStartDate={() => undefined} focus={null} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Create plan" }));
    expect(await screen.findByText("Rice")).toBeInTheDocument();
    expect(screen.getByText(/10 \/ 20 bag/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Taungoo/ }));
    expect(await screen.findByText("Oil")).toBeInTheDocument();
    expect(screen.queryByText("Rice")).not.toBeInTheDocument();
  });

  it("renders only the routes the comparison returned", async () => {
    vi.mocked(api.allocationPlan).mockResolvedValueOnce(samplePlan);
    vi.mocked(api.compareTownshipRoutes).mockResolvedValue({
      plan_id: "p1",
      township_id: "bago",
      depot_region: "east",
      alternatives_available: true,
      rainfall_mm: 12.5,
      discharge_m3_s: 3.4,
      flood_probability: 0.8,
      risk_band: "high",
      alternatives: [
        {
          option_index: 1,
          label: "Option 1",
          path: [],
          distance_m: 12000,
          duration_s: 900,
          routing_method: "osrm_road",
          flood_exposure: "clear",
          blocked_segments: [],
          rainfall_mm: 12.5,
          discharge_m3_s: 3.4,
          recommended: true,
          selected: false,
        },
        {
          option_index: 2,
          label: "Option 2",
          path: [],
          distance_m: 18000,
          duration_s: 1400,
          routing_method: "osrm_road",
          flood_exposure: "penalized",
          blocked_segments: [],
          rainfall_mm: 12.5,
          discharge_m3_s: 3.4,
          recommended: false,
          selected: false,
        },
      ],
    });
    render(
      <ResourceAllocationDashboard startDate="2026-10-20" onStartDate={() => undefined} focus={null} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Create plan" }));
    expect(await screen.findByRole("button", { name: /Taungoo/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Option 1/ })).not.toBeInTheDocument();
    expect(api.compareTownshipRoutes).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Other roads" }));
    expect(await screen.findByRole("button", { name: /Option 1/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Option 2/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Option 3/ })).not.toBeInTheDocument();
    expect(screen.queryByText(/Only one route is available/i)).not.toBeInTheDocument();
  });

  it("opens the print preview for a ready plan", async () => {
    vi.mocked(api.allocationPlan).mockResolvedValueOnce(samplePlan);
    render(
      <ResourceAllocationDashboard startDate="2026-10-20" onStartDate={() => undefined} focus={null} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Create plan" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Print preview" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Print preview" }));
    const dialog = screen.getByRole("dialog", { name: "Allocation report" });
    expect(within(dialog).getByText("Resource allocation report")).toBeInTheDocument();
    const townships = within(dialog).getByRole("table", { name: "Townships" });
    expect(within(townships).getByRole("cell", { name: "Taungoo" })).toBeInTheDocument();
    expect(within(dialog).queryByText("Needed")).not.toBeInTheDocument();
    const items = within(dialog).getByRole("table", { name: "Line items" });
    const rice = within(items).getByRole("row", { name: /Rice/ });
    expect(rice).toHaveTextContent("bag");
    expect(rice).toHaveTextContent("20");
    expect(rice).toHaveTextContent("10");
  });
});
