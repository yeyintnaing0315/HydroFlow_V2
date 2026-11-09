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
    floodCasesHighSevere: vi.fn().mockResolvedValue({
      counts: { total: 0, severe: 0, high: 0, recorded: 0, model: 0 },
      by_year: [],
      disclaimer: "",
      events: [],
    }),
    confirmAllocationPlan: vi.fn().mockResolvedValue({
      plan_id: "p1",
      status: "confirmed",
      prediction_run_id: null,
    }),
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
  status: "draft" as const,
  rows: [
    {
      township_id: "bago",
      township_name: "Bago",
      latitude: 17.33,
      longitude: 96.48,
      population: 20,
      affected_male: 9,
      affected_female: 11,
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
      affected_male: 5,
      affected_female: 5,
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

    expect(screen.getByText(/High and severe only/)).toBeInTheDocument();
    expect(screen.getByLabelText("Allocation summary")).toBeInTheDocument();
    const planTable = screen.getByRole("region", { name: "Allocation plan table" });
    expect(within(planTable).getByRole("columnheader", { name: "Township" })).toBeInTheDocument();
    expect(within(planTable).getByRole("columnheader", { name: "Male" })).toBeInTheDocument();
    expect(within(planTable).getByRole("columnheader", { name: "Female" })).toBeInTheDocument();
    expect(within(planTable).getByRole("columnheader", { name: "People" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create Allocation Plan" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "East and west stock" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Plans need verified depot stock/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Route map context")).toBeInTheDocument();
    const details = screen.getByLabelText("Allocation details");
    expect(within(details).getByText("All high and severe")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Route map context")).queryByText("All high and severe")).not.toBeInTheDocument();
    expect(
      details.compareDocumentPosition(screen.getByLabelText("Route map context")) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(within(screen.getByLabelText("Allocation summary")).getByText("Estimated fund")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Township allocations" })).not.toBeInTheDocument();
    expect(screen.queryByText(/Inventory unavailable/)).not.toBeInTheDocument();
    await waitFor(() => expect(api.census).toHaveBeenCalled());
    await waitFor(() => expect(api.inventory).toHaveBeenCalledWith("east"));
    expect(api.inventory).toHaveBeenCalledWith("west");
    expect(api.helpSummary).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Create Allocation Plan" }));

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

    const details = screen.getByLabelText("Allocation details");
    expect(within(details).getByText("Bago")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Route map context")).queryByText("Bago")).not.toBeInTheDocument();
    expect(within(details).getAllByText("High").length).toBeGreaterThan(0);
    expect(
      within(screen.getByRole("region", { name: "Allocation plan table" })).getAllByText("Bago").length,
    ).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Estimate" })).toBeInTheDocument();
    expect(screen.queryByText(/No high or severe townships for this date/)).not.toBeInTheDocument();
    vi.mocked(api.helpSummary).mockResolvedValueOnce({ expected_affected_people: 120 } as never);
    fireEvent.click(screen.getByRole("button", { name: "Estimate" }));
    await waitFor(() => expect(api.helpSummary).toHaveBeenCalled());
    await waitFor(() => {
      const panel = screen.getByRole("region", { name: "Allocation plan table" });
      expect(within(panel).queryByText(/No high or severe townships for this date/)).not.toBeInTheDocument();
      expect(within(panel).getByRole("table")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "Create Allocation Plan" }));
    await waitFor(() => expect(api.allocationPlan).toHaveBeenCalled());
    expect(api.allocationPlan).toHaveBeenCalledWith(
      expect.objectContaining({
        min_priority: "high",
        include_all_high_severe: false,
        township_ids: ["MMR007001701"],
        expected_affected_overrides: { MMR007001701: 120 },
      }),
    );
  });

  it("shows compact plan columns on the dashboard after planning", async () => {
    vi.mocked(api.allocationPlan).mockResolvedValueOnce(samplePlan);
    render(
      <ResourceAllocationDashboard startDate="2026-10-20" onStartDate={() => undefined} focus={null} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Create Allocation Plan" }));
    const supplies = await screen.findByRole("region", { name: "Allocation plan table" });
    expect(within(supplies).getByRole("cell", { name: "Bago" })).toBeInTheDocument();
    expect(within(supplies).getByRole("columnheader", { name: "Date" })).toBeInTheDocument();
    expect(within(supplies).getByRole("columnheader", { name: "Route" })).toBeInTheDocument();
    expect(within(supplies).queryByRole("columnheader", { name: /Rice/ })).not.toBeInTheDocument();
    expect(within(supplies).getAllByRole("cell", { name: "2026-10-20" }).length).toBeGreaterThan(0);
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
    fireEvent.click(screen.getByRole("button", { name: "Create Allocation Plan" }));
    expect(await screen.findByRole("button", { name: /Taungoo/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Option 1/ })).not.toBeInTheDocument();
    expect(api.compareTownshipRoutes).not.toHaveBeenCalled();
    expect(screen.queryByRole("heading", { name: "Routes" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Other roads/i })).not.toBeInTheDocument();
  });

  it("opens the print preview for a ready plan", async () => {
    vi.mocked(api.allocationPlan).mockResolvedValueOnce(samplePlan);
    render(
      <ResourceAllocationDashboard startDate="2026-10-20" onStartDate={() => undefined} focus={null} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Create Allocation Plan" }));
    const printButton = await screen.findByRole("button", { name: "Print preview" });
    expect(printButton).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Confirm plan" }));
    await waitFor(() => expect(api.confirmAllocationPlan).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole("button", { name: "Print preview" })).toBeEnabled());
    const deductions = screen.getByLabelText("Depot stock reduced");
    expect(within(deductions).getByText("Rice")).toBeInTheDocument();
    expect(within(deductions).getByText(/−10 bag/)).toBeInTheDocument();
    expect(within(deductions).getByText("Oil")).toBeInTheDocument();
    expect(within(deductions).getByText(/−4 bottle/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Print preview" }));
    const dialog = screen.getByRole("dialog", { name: "Allocation report" });
    expect(within(dialog).getByText("Resource allocation plan")).toBeInTheDocument();
    const supplies = within(dialog).getByLabelText("Township supplies");
    expect(within(supplies).getByRole("heading", { name: "Taungoo" })).toBeInTheDocument();
    expect(within(supplies).getAllByText("Rice").length).toBeGreaterThan(0);
    expect(within(supplies).getAllByText("Box").length).toBeGreaterThan(0);
    expect(within(dialog).getByRole("heading", { name: "Route map" })).toBeInTheDocument();
    expect(within(dialog).getByText(/Fund allocated/i)).toBeInTheDocument();
  });

  it("keeps fund money out of the required resource unit count", async () => {
    vi.mocked(api.allocationPlan).mockResolvedValueOnce({
      ...samplePlan,
      totals: { affected_population: 10, available_stock_units: 100, resources_needed_units: 100_030 },
      rows: [
        {
          ...samplePlan.rows[0],
          population: 10,
          affected_male: 4,
          affected_female: 6,
          line_items: [
            { category_code: "foods", item_code: "rice", name: "Rice", unit: "bag", requested: 10, allocated: 10 },
            { category_code: "fund", item_code: null, name: "Fund", unit: "mmk", requested: 100_000, allocated: 100_000 },
          ],
        },
      ],
    });
    render(
      <ResourceAllocationDashboard startDate="2026-10-20" onStartDate={() => undefined} focus={null} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Create Allocation Plan" }));
    const summary = await screen.findByLabelText("Allocation summary");
    expect(within(summary).getByText("10 units")).toBeInTheDocument();
    expect(within(summary).getByText("100,000 MMK")).toBeInTheDocument();
    expect(within(summary).queryByText(/100,030/)).not.toBeInTheDocument();
    const details = screen.getByLabelText("Allocation details");
    const mapColumn = details.closest(".allocation-map-column");
    expect(mapColumn).not.toBeNull();
    expect(mapColumn?.contains(screen.getByLabelText("Route map context"))).toBe(true);
    expect(
      details.compareDocumentPosition(screen.getByLabelText("Route map context")) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("shows which depot stock to add when the plan is blocked", async () => {
    const openInventory = vi.fn();
    const error = new Error("We cannot create a plan if there is a shortage of resources.");
    Object.assign(error, {
      detail: {
        shortages: [
          {
            category_code: "foods",
            item_code: "rice",
            name: "Rice",
            unit: "bag",
            requested: 9499,
            available: 1200,
            unmet: 8299,
            depot_region: "west",
          },
          {
            category_code: "foods",
            item_code: "oil",
            name: "Oil",
            unit: "bottle",
            requested: 9499,
            available: 0,
            unmet: 9499,
            depot_region: "west",
          },
        ],
      },
    });
    vi.mocked(api.allocationPlan).mockRejectedValueOnce(error);
    render(
      <ResourceAllocationDashboard
        startDate="2026-10-20"
        onStartDate={() => undefined}
        focus={null}
        onOpenInventory={openInventory}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Create Allocation Plan" }));
    const notice = await screen.findByRole("alert");
    expect(within(notice).getByText("Add inventory before this plan can be created")).toBeInTheDocument();
    expect(within(notice).getByText("Pyay depot (west)")).toBeInTheDocument();
    expect(within(notice).getByText("Rice")).toBeInTheDocument();
    expect(within(notice).getByText(/add 8,299 bags/)).toBeInTheDocument();
    expect(within(notice).getByText("Oil")).toBeInTheDocument();
    expect(within(notice).getByText(/add 9,499 bottles/)).toBeInTheDocument();
    fireEvent.click(within(notice).getByRole("button", { name: "Open inventory" }));
    expect(openInventory).toHaveBeenCalledOnce();
  });
});
