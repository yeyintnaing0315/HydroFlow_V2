import type {
  AdminHierarchyResponse,
  Alert,
  AllocationConfirmResult,
  AllocationPlanHistoryItem,
  AllocationPlanRequest,
  AllocationPlanResponse,
  DepotNetworkRoutesResponse,
  AllocationStoreStatus,
  TownshipRouteComparison,
  BagoAreasResponse,
  CensusResponse,
  FloodCaseCatalogResponse,
  FloodHistoryResponse,
  ForecastResponse,
  HealthResponse,
  HelpBriefResponse,
  HelpDay,
  HelpResponse,
  HistoricalResponse,
  InundationProduct,
  CatalogCategoryCreate,
  CatalogItemTypeCreate,
  InventoryDetection,
  InventoryDetectionConfirm,
  InventoryEntry,
  InventoryLocationsResponse,
  InventorySnapshot,
  JobRun,
  OfficialWarning,
  OutlookResponse,
  PredictionMapScoresResponse,
  PredictionTimelineInput,
  RegionForecastResponse,
  PredictionTimelineResponse,
  PredictInput,
  PredictResponse,
  RiskResult,
  RoutePlanRequest,
  RoutePlanResponse,
  SettlementPoint,
  SourceStatus,
  TopographyResponse,
  Township,
} from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "/api";

import { formatApiDetail } from "./lib/formatError";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body && !(init.body instanceof FormData) ? { "Content-Type": "application/json" } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`.trim();
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (body.detail !== undefined) {
        detail = formatApiDetail(body.detail);
      }
    } catch {
      // Keep the HTTP status when the server does not return JSON.
    }
    throw new ApiError(detail, response.status);
  }
  return response.json() as Promise<T>;
}

function query(latitude: number, longitude: number): string {
  return new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
  }).toString();
}

function recentHistoryQuery(latitude: number, longitude: number): string {
  const end = new Date();
  const start = new Date(end);
  start.setUTCDate(end.getUTCDate() - 5);
  end.setUTCDate(end.getUTCDate() - 1);
  return new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    start: start.toISOString().slice(0, 10),
    end: end.toISOString().slice(0, 10),
  }).toString();
}

export const api = {
  health: () => request<HealthResponse>("/health"),
  predict: (input: PredictInput) =>
    request<PredictResponse>("/predict", { method: "POST", body: JSON.stringify(input) }),
  outlook: (input: PredictInput) =>
    request<OutlookResponse>("/outlook", { method: "POST", body: JSON.stringify(input) }),
  predictionTimeline: (input: PredictionTimelineInput) =>
    request<PredictionTimelineResponse>("/prediction/timeline", {
      method: "POST",
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(180_000),
    }),
  predictionCalendarBounds: () =>
    request<{
      history_start: string;
      operational_start?: string;
      labeled_start?: string | null;
      labeled_end?: string | null;
      history_end: string;
      forecast_end: string;
      select_max: string;
    }>("/prediction/calendar-bounds"),
  predictionHazardSurface: (townshipId: string) =>
    request<{
      township_id: string;
      status: string;
      detail?: string;
      jrc_depth_100y_max_m?: number | null;
      jrc_pct_inundated_100y?: number | null;
      hand_min_m?: number | null;
      hand_pct_lt_2m?: number | null;
      worldcover_pct_built_floodplain?: number | null;
      worldcover_pct_crop_floodplain?: number | null;
      hazard_preview_path?: string | null;
      hydrobasin_id?: string | null;
    }>(`/prediction/township/${encodeURIComponent(townshipId)}/hazard-surface`),
  predictionMapScores: (date: string, districtId?: string) => {
    const params = new URLSearchParams({ date });
    if (districtId) params.set("district_id", districtId);
    return request<PredictionMapScoresResponse>(`/prediction/map-scores?${params}`);
  },
  help: (input: PredictInput) =>
    request<HelpResponse>("/help", { method: "POST", body: JSON.stringify(input) }),
  helpSummary: (input: PredictInput) =>
    request<HelpDay>("/help/summary", { method: "POST", body: JSON.stringify(input) }),
  helpBrief: () => request<HelpBriefResponse>("/help-brief?limit=5"),
  floodCasesHighSevere: (params?: {
    level?: "all" | "high" | "severe";
    source?: "all" | "recorded" | "model";
    view?: "events" | "days";
    year?: number;
    limit?: number;
    offset?: number;
  }) => {
    const search = new URLSearchParams();
    if (params?.level) search.set("level", params.level);
    if (params?.source) search.set("source", params.source);
    if (params?.view) search.set("view", params.view);
    if (params?.year != null) search.set("year", String(params.year));
    if (params?.limit != null) search.set("limit", String(params.limit));
    if (params?.offset != null) search.set("offset", String(params.offset));
    const query = search.toString();
    return request<FloodCaseCatalogResponse>(`/flood-cases/high-severe${query ? `?${query}` : ""}`);
  },
  allocationNetworkRoutes: (legs: {
    township_id: string;
    depot_region: "east" | "west";
    depot_latitude: number;
    depot_longitude: number;
    township_latitude: number;
    township_longitude: number;
  }[]) =>
    request<DepotNetworkRoutesResponse>("/allocation/network-routes", {
      method: "POST",
      body: JSON.stringify({ legs }),
      signal: AbortSignal.timeout(120_000),
    }),
  allocationPlan: (input: AllocationPlanRequest) =>
    request<AllocationPlanResponse>("/allocation/plan", {
      method: "POST",
      body: JSON.stringify(input),
      signal: AbortSignal.timeout(120_000),
    }),
  allocationStores: () => request<AllocationStoreStatus[]>("/allocation/stores"),
  verifyAllocationStore: (region: "east" | "west", note?: string) =>
    request<AllocationStoreStatus>(`/allocation/stores/${region}/verify`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),
  allocationPlans: () => request<AllocationPlanHistoryItem[]>("/allocation/plans"),
  allocationPlanDetail: (planId: string) => request<AllocationPlanResponse>(`/allocation/plans/${planId}`),
  compareTownshipRoutes: (planId: string, townshipId: string) =>
    request<TownshipRouteComparison>(
      `/allocation/plans/${planId}/townships/${encodeURIComponent(townshipId)}/routes`,
      { method: "POST", signal: AbortSignal.timeout(20_000) },
    ),
  selectTownshipRoute: (planId: string, townshipId: string, optionIndex: number) =>
    request<TownshipRouteComparison>(
      `/allocation/plans/${planId}/townships/${encodeURIComponent(townshipId)}/routes/select`,
      { method: "POST", body: JSON.stringify({ option_index: optionIndex }) },
    ),
  confirmAllocationPlan: (planId: string) =>
    request<AllocationConfirmResult>(`/allocation/plans/${planId}/confirm`, { method: "POST" }),
  townships: () => request<Township[]>("/townships"),
  bagoAreas: () => request<BagoAreasResponse>("/bago-areas"),
  census: () => request<CensusResponse>("/census"),
  forecast: (latitude: number, longitude: number) =>
    request<ForecastResponse>(`/forecast?${query(latitude, longitude)}`),
  topography: (latitude: number, longitude: number) =>
    request<TopographyResponse>(`/topography?${query(latitude, longitude)}`),
  alerts: () => request<Alert[]>("/alerts"),
  historical: (
    latitude: number,
    longitude: number,
    start?: string,
    end?: string,
    townshipId?: string,
  ) => {
    const params = new URLSearchParams(
      start && end
        ? {
            latitude: String(latitude),
            longitude: String(longitude),
            start,
            end,
          }
        : Object.fromEntries(new URLSearchParams(recentHistoryQuery(latitude, longitude))),
    );
    if (townshipId) params.set("township_id", townshipId);
    return request<HistoricalResponse>(`/historical?${params}`);
  },
  floodHistory: () => request<FloodHistoryResponse>("/flood-history?limit=8"),
  planRoute: (input: RoutePlanRequest) =>
    request<RoutePlanResponse>("/routes", { method: "POST", body: JSON.stringify(input) }),
  sources: () => request<SourceStatus[]>("/sources"),
  officialWarnings: () => request<OfficialWarning[]>("/official-warnings"),
  runs: () => request<JobRun[]>("/runs"),
  riskResults: () => request<RiskResult[]>("/risk-results"),
  inundationProducts: () => request<InundationProduct[]>("/inundation-products"),
  runPrediction: (adminKey: string) =>
    request<JobRun>("/runs/prediction", {
      method: "POST",
      headers: { "X-Admin-Key": adminKey },
    }),
  adminAreas: (search?: string, includeGeometry = false) => {
    const query = new URLSearchParams({ max_level: "5" });
    if (search) query.set("search", search);
    if (includeGeometry) query.set("include_geometry", "true");
    return request<AdminHierarchyResponse>(`/admin-areas?${query}`);
  },
  inventory: (region: "east" | "west") => request<InventorySnapshot>(`/inventory/${region}`),
  inventoryLocations: () => request<InventoryLocationsResponse>("/inventory"),
  addInventory: (region: "east" | "west", entry: InventoryEntry) =>
    request<InventorySnapshot>(`/inventory/${region}/entries`, {
      method: "POST",
      body: JSON.stringify(entry),
    }),
  createInventoryCategory: (body: CatalogCategoryCreate) =>
    request<InventoryLocationsResponse>("/inventory/catalog/categories", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createInventoryItemType: (categoryCode: string, body: CatalogItemTypeCreate) =>
    request<InventoryLocationsResponse>(
      `/inventory/catalog/categories/${encodeURIComponent(categoryCode)}/item-types`,
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
  detectInventory: (categoryCode: string, image: Blob) => {
    const body = new FormData();
    body.append("category_code", categoryCode);
    body.append("image", image, "capture.jpg");
    return request<InventoryDetection>("/inventory/detect", { method: "POST", body });
  },
  detectInventoryVideo: (categoryCode: string, video: Blob) => {
    const body = new FormData();
    body.append("category_code", categoryCode);
    body.append("video", video, "capture.mp4");
    return request<InventoryDetection>("/inventory/detect/video", { method: "POST", body });
  },
  confirmDetection: (region: "east" | "west", detection: InventoryDetectionConfirm) =>
    request<InventorySnapshot>(`/inventory/${region}/detections/confirm`, {
      method: "POST",
      body: JSON.stringify(detection),
    }),
  settlements: (adminAreaCode?: string) => {
    const query = new URLSearchParams({ limit: "5000" });
    if (adminAreaCode) query.set("admin_area_code", adminAreaCode);
    return request<SettlementPoint[]>(`/settlements?${query}`);
  },
  predictionRegionForecast: (asOf: string, districtId?: string) => {
    const params = new URLSearchParams({ as_of: asOf });
    if (districtId) params.set("district_id", districtId);
    return request<RegionForecastResponse>(`/prediction/region-forecast?${params}`);
  },
};
