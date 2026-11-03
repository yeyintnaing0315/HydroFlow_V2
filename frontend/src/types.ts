import type { Geometry } from "geojson";

export type LoadState = "loading" | "ready" | "empty" | "error";
export type RiskLevel = "low" | "moderate" | "high" | "severe";
export type PageId = "home" | "prediction" | "allocation" | "inventory";

export interface Coordinates {
  latitude: number;
  longitude: number;
}

export interface PredictInput extends Coordinates {
  date: string;
  township_id: string;
  township_name_en?: string;
}

export interface Township extends Coordinates {
  township_id: string;
  township: string;
}

export interface InventoryClassItem {
  code: string | null;
  name: string;
  quantity: number;
  unit: string;
  capacity?: number;
}

export interface InventoryClass {
  code: string;
  name: string;
  entry_mode: "scan_or_manual" | "manual_only";
  quantity: number;
  capacity?: number;
  items: InventoryClassItem[];
}

export interface InventoryMovementRow {
  id: number;
  category_code: string;
  item_code: string | null;
  name: string;
  class_name: string;
  direction: "in" | "out";
  entry_mode: "manual" | "scan";
  quantity: number;
  unit: string;
  created_at: string;
}

export interface InventorySnapshot {
  region: "east" | "west";
  location: "Bago East" | "Bago West";
  classes: InventoryClass[];
  movements: InventoryMovementRow[];
}

export interface InventoryDetectionItem {
  item_code: string;
  quantity: number;
  confidence: number;
}

export interface InventoryDetection {
  category_code: string;
  items: InventoryDetectionItem[];
}

export interface InventoryEntry {
  category_code: string;
  item_code: string | null;
  quantity: number;
  entry_mode: "manual" | "scan";
  direction?: "in" | "out";
}

export interface CatalogCategoryCreate {
  code: string;
  name: string;
  entry_mode: "scan_or_manual" | "manual_only";
  sort_order?: number;
}

export interface CatalogItemTypeCreate {
  code: string;
  name: string;
  unit: string;
  sort_order?: number;
}

export interface InventoryLocationsResponse {
  locations: InventorySnapshot[];
}

export interface AdminTownship extends Coordinates {
  id: string;
  slug: string;
  name_en: string;
  name_local: string;
  geometry?: Geometry | null;
  level: number;
  area_type: string;
  coverage_status: string;
}

export interface AdminDistrict extends AdminTownship {
  townships: AdminTownship[];
}

export interface BagoAreasResponse extends Coordinates {
  source: string;
  dataset_version: string;
  license: string;
  coverage_note: string;
  region_id: string;
  region_name_en: string;
  region_name_local: string;
  geometry?: Geometry | null;
  districts: AdminDistrict[];
}

export interface OutlookDay {
  date: string;
  precipitation_mm: number;
  discharge_m3_s: number;
  temperature_c?: number | null;
  relative_humidity_pct?: number | null;
  wind_speed_m_s?: number | null;
  rainfall_7d_mm?: number | null;
  rainfall_30d_mm?: number | null;
  flood_probability: number;
  predicted_flood: boolean;
  risk_score: number;
  risk_level: RiskLevel;
  alert_recorded: boolean;
  forecast_horizon_hours: number;
  evidence_type: "model_prediction";
  probability_status: "uncalibrated_academic_score";
  input_freshness: Record<string, string | null>;
  uncertainty: string;
}

export interface OutlookResponse {
  township_id: string;
  source: string;
  model_version: string;
  in_training_set?: boolean;
  days: OutlookDay[];
}

export type PeriodType = "historical" | "current" | "forecast";
export type PredictionDataStatus =
  | "model_estimate"
  | "observed_impact"
  | "unavailable"
  | "insufficient_features";

export interface PredictionTimelineDay {
  date: string;
  period_type: PeriodType;
  flood_probability: number | null;
  predicted_flood: boolean | null;
  probability_risk_level: RiskLevel | null;
  risk_level: RiskLevel | "unknown";
  hydrology_risk_score: number | null;
  hydrology_risk_level: RiskLevel | null;
  rainfall_mm: number | null;
  discharge_m3_s: number | null;
  temperature_c?: number | null;
  relative_humidity_pct?: number | null;
  wind_speed_m_s?: number | null;
  rainfall_7d_mm?: number | null;
  impact_level: "none" | RiskLevel | "unknown";
  potentially_exposed_population: number | null;
  potentially_affected_population: number | null;
  observed_flood: boolean | null;
  recorded_affected_people: number | null;
  data_status: PredictionDataStatus;
  evidence_type: "model_prediction" | "archive_reference" | "none";
  probability_status: "uncalibrated_academic_score" | null;
  forecast_horizon_hours: number;
  input_freshness: Record<string, string | null>;
  uncertainty: string;
  key_factors: string[];
  secondary_flood_probability?: number | null;
  secondary_probability_risk_level?: RiskLevel | null;
  gfm_validation?: {
    water_fraction?: number | null;
    status?: string;
    detail?: string | null;
  } | null;
}

export interface PredictionTimelineResponse {
  township_id: string;
  as_of: string;
  timezone: string;
  model_version: string;
  secondary_model_version?: string | null;
  in_training_set: boolean;
  generated_at: string;
  potentially_exposed_population: number | null;
  disclaimer: string;
  days: PredictionTimelineDay[];
}

export interface TownshipMapScore {
  township_id: string;
  township_name: string;
  latitude: number | null;
  longitude: number | null;
  parent_id: number | null;
  flood_probability: number | null;
  probability_risk_level: RiskLevel | null;
  secondary_flood_probability?: number | null;
  secondary_probability_risk_level?: RiskLevel | null;
  risk_level: RiskLevel | "unknown";
  rainfall_mm: number | null;
  horizon_3d?: number | null;
  horizon_7d?: number | null;
  data_status: "model_estimate" | "unavailable" | "insufficient_features";
}

export interface PredictionMapScoresResponse {
  date: string;
  model_version: string;
  secondary_model_version?: string | null;
  cached: boolean;
  scores: TownshipMapScore[];
}

export interface PredictionTimelineInput extends PredictInput {
  as_of?: string;
}

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  database?: { ready: boolean; missing_tables: string[]; revision?: string | null };
  models?: { flood: boolean; help: boolean; allocation: boolean };
}

export interface PredictResponse {
  flood_probability: number;
  predicted_flood: boolean;
  threshold: number;
  model_version: string;
  alert_recorded: boolean;
  evidence_type: "model_prediction";
  probability_status: "uncalibrated_academic_score";
  uncertainty: string;
}

export interface SourceStatus {
  key: string;
  name: string;
  kind: string;
  enabled: boolean;
  unavailable_reason?: string | null;
  attribution: string;
  license_name?: string | null;
  url: string;
}

export interface AdminArea {
  id: string;
  parent_id?: string | null;
  level: number;
  area_type: string;
  name_en: string;
  name_local?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  geometry?: Geometry | null;
  coverage_status: string;
}

export interface AdminHierarchyResponse {
  source: string;
  dataset_version: string;
  license: string;
  coverage_note: string;
  areas: AdminArea[];
}

export interface OfficialWarning {
  id: number;
  source: string;
  external_id: string;
  issued_at: string;
  effective_at?: string | null;
  expires_at?: string | null;
  severity: string;
  status: string;
  message: string;
  source_url?: string | null;
  coverage: Record<string, unknown>;
}

export interface JobRun {
  id: number;
  job_name: string;
  scheduled_for: string;
  started_at: string;
  finished_at?: string | null;
  status: string;
  attempt: number;
  model_version?: string | null;
  freshness: Record<string, unknown>;
  coverage: Record<string, unknown>;
  error?: string | null;
}

export interface RiskResult {
  id: number;
  admin_area_id?: number | null;
  admin_area_code?: string | null;
  admin_area_name?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  valid_at: string;
  forecast_horizon_hours: number;
  evidence_type: "heuristic_risk" | "model_prediction";
  risk_level: RiskLevel;
  risk_score?: number | null;
  probability?: number | null;
  input_freshness: Record<string, unknown>;
  supporting_evidence: Record<string, unknown>;
  uncertainty: Record<string, unknown>;
}

export interface InundationProduct {
  id: number;
  evidence_type: "observed_inundation";
  observed_at: string;
  retrieved_at: string;
  geometry: Geometry;
  quality: string;
  affected_population?: number | null;
  population_source?: string | null;
  metadata: Record<string, unknown>;
}

export interface SettlementPoint extends Coordinates {
  id: number;
  source_code: string;
  admin_area_id?: number | null;
  name_en: string;
  name_local?: string | null;
  settlement_type: string;
  verification_status: string;
  note: string;
}

export interface RiskResponse {
  score: number;
  level: RiskLevel;
  label: string;
}

export interface ForecastPoint {
  timestamp: string;
  precipitation_mm?: number | null;
  temperature_c?: number | null;
  relative_humidity_pct?: number | null;
  wind_speed_m_s?: number | null;
  discharge_m3_s?: number | null;
}

export interface ForecastResponse extends Coordinates {
  points: ForecastPoint[];
}

export interface TopographyResponse extends Coordinates {
  elevation_m: number;
  dataset: string;
  vertical_datum: string;
  vertical_datum_epsg: string;
  unit: string;
  source: string;
  note: string;
}

export interface TopographyResponse extends Coordinates {
  elevation_m: number;
  dataset: string;
  vertical_datum: string;
  vertical_datum_epsg: string;
  unit: string;
  source: string;
  note: string;
}

export interface Alert {
  id: number;
  location_id: number;
  issued_at: string;
  level: RiskLevel;
  message: string;
  source: string;
}

export interface HistoricalPoint {
  date: string;
  precipitation_mm?: number | null;
  temperature_c?: number | null;
  relative_humidity_pct?: number | null;
  wind_speed_m_s?: number | null;
  flood_probability?: number | null;
  risk_level?: RiskLevel | null;
}

export interface HistoricalResponse extends Coordinates {
  points: HistoricalPoint[];
}

export interface FloodHistoryRecord {
  date: string;
  township_id: string;
  township: string;
  latitude: number;
  longitude: number;
  households?: number | null;
  affected_people?: number | null;
  impact_severity: "none" | RiskLevel;
}

export interface FloodHistoryResponse {
  source: string;
  disclaimer: string;
  matched_records: number;
  records: FloodHistoryRecord[];
}

export interface FloodCaseItem {
  place: string;
  township_id: string;
  depot: string;
  source: "recorded" | "model";
  level: "high" | "severe";
  start_date: string;
  end_date: string;
  peak_date: string;
  peak_score?: number | null;
  households?: number | null;
  affected_people?: number | null;
  days: number;
  overlap: boolean;
}

export interface FloodCaseCatalogResponse {
  source_file: string;
  view: "events" | "days";
  disclaimer: string;
  counts: {
    total: number;
    severe: number;
    high: number;
    recorded: number;
    model: number;
    overlap: number;
  };
  by_year: { year: number; count: number }[];
  events: FloodCaseItem[];
}

export type AssistancePriority = "none" | RiskLevel;

export interface HelpDay {
  date: string;
  help_probability: number;
  predicted_help: boolean;
  expected_affected_people: number;
  expected_households: number;
  affected_male?: number | null;
  affected_female?: number | null;
  impact_source?: string | null;
  assistance_priority: AssistancePriority;
  shelter_kits: number;
  food_rations_3d: number;
  drinking_water_liters_3d: number;
}

export interface HelpResponse {
  township_id: string;
  source: string;
  model_version: string;
  disclaimer: string;
  days: HelpDay[];
}

export interface HelpBriefResponse {
  source: string;
  disclaimer: string;
  recorded_flood_days: number;
  recorded_households: number;
  recorded_affected_people: number;
  townships_with_impact: number;
  highest_impacts: FloodHistoryRecord[];
}

export interface DepotNetworkLeg {
  township_id: string;
  depot_region: "east" | "west";
  depot_latitude: number;
  depot_longitude: number;
  township_latitude: number;
  township_longitude: number;
}

export interface DepotNetworkRoute {
  township_id: string;
  depot_region: "east" | "west";
  path: Coordinates[];
  distance_m: number | null;
  routing_method: "osrm_road" | "straight_line_fallback";
}

export interface DepotNetworkRoutesResponse {
  routes: DepotNetworkRoute[];
  disclaimer: string;
}

export interface AllocationPlanRequest {
  date: string;
  warehouse_region?: "east" | "west" | "auto";
  min_priority?: AssistancePriority;
  township_ids?: string[];
  include_all_high_severe?: boolean;
  commit_inventory?: boolean;
  vehicle_profile?: "car" | "truck" | "fly";
  /** Township id → affected people from dashboard estimate (matches help summary / prediction). */
  expected_affected_overrides?: Record<string, number>;
}

export interface AllocationLineItem {
  category_code: string;
  item_code: string | null;
  name: string;
  unit: string;
  requested: number;
  allocated: number;
}

export interface TownshipRouteOption {
  option_index: number;
  label: string;
  path: Coordinates[];
  distance_m: number | null;
  duration_s: number | null;
  routing_method: string;
  flood_exposure: "clear" | "penalized" | "blocked" | "unknown";
  blocked_segments: AllocationBlockedSegment[];
  rainfall_mm: number | null;
  discharge_m3_s: number | null;
  recommended: boolean;
  selected: boolean;
}

export interface TownshipRouteComparison {
  plan_id: string;
  township_id: string;
  depot_region: "east" | "west";
  alternatives: TownshipRouteOption[];
  alternatives_available: boolean;
  rainfall_mm: number | null;
  discharge_m3_s: number | null;
  flood_probability: number | null;
  risk_band: string | null;
}

export interface AllocationTownshipRow {
  township_id: string;
  township_name: string;
  latitude: number;
  longitude: number;
  population: number;
  affected_male?: number;
  affected_female?: number;
  priority: AssistancePriority;
  resources_label: string;
  quantities_label: string;
  line_items: AllocationLineItem[];
  route_id: string;
  depot_region: "east" | "west";
  has_shortage: boolean;
  flood_probability?: number | null;
  risk_band?: string | null;
  rainfall_mm?: number | null;
  discharge_m3_s?: number | null;
  requested_total?: number;
  allocated_total?: number;
  route_options?: TownshipRouteOption[];
}

export interface AllocationShortage {
  category_code: string;
  item_code: string | null;
  name: string;
  unit: string;
  requested: number;
  available: number;
  unmet: number;
  depot_region: "east" | "west";
}

export interface AllocationWarehouse {
  id: string;
  name: string;
  region: "east" | "west";
  latitude: number;
  longitude: number;
}

export interface AllocationRouteSummary {
  route_id: string;
  stop_count: number;
  path: Coordinates[];
  depot_region: "east" | "west";
  routing_method?: string;
  blocked_segments?: AllocationBlockedSegment[];
  distance_m?: number | null;
  duration_s?: number | null;
  plan: RoutePlanResponse | null;
}

export interface AllocationPlanResponse {
  plan_id: string;
  planning_date: string;
  warehouse: AllocationWarehouse;
  warehouses: AllocationWarehouse[];
  totals: {
    affected_population: number;
    available_stock_units: number | null;
    resources_needed_units: number;
  };
  rows: AllocationTownshipRow[];
  shortages: AllocationShortage[];
  routes: AllocationRouteSummary[];
  model_version: string;
  disclaimer: string;
  status?: "draft" | "confirmed";
  prediction_run_id?: number | null;
  unverified_stores?: AllocationStoreStatus[];
}

export interface RouteStop {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
}

export interface RoutePlanRequest {
  origin: RouteStop;
  stops: RouteStop[];
  vehicle_profile: "car" | "truck" | "fly";
  service_minutes: number;
  return_to_origin: boolean;
}

export interface RouteWaypoint extends Coordinates {
  stop_id: string;
  name: string;
  arrival_time?: string | null;
  kind: string;
}

export interface RoutePlanResponse {
  plan_id: string;
  agency_id?: string | null;
  state: string;
  vehicle_profile: "car" | "truck" | "fly";
  distance_km?: number | null;
  duration?: string | null;
  duration_minutes?: number | null;
  waypoints: RouteWaypoint[];
  path: Coordinates[];
  unaffected_stop_ids: string[];
  disclaimer: string;
  assumptions: string[];
}

export interface SexCount {
  total: number;
  male: number;
  female: number;
}

export interface CensusAgeGroup {
  label: string;
  min_age: number;
  max_age: number | null;
  total: SexCount;
  urban: SexCount;
  rural: SexCount;
}

export interface HouseholdSizeBucket {
  size: string;
  households: number;
}

export interface DwellingCount {
  total: number;
  apartment: number;
  brick: number;
  semi_brick: number;
  wooden: number;
  bamboo: number;
  hut: number;
  other: number;
}

export interface HouseholdSituation {
  total: number;
  by_size: HouseholdSizeBucket[];
  by_dwelling: DwellingCount;
}

export interface DwellingTypeLabel {
  key: keyof Omit<DwellingCount, "total">;
  name_local: string;
  name_en: string;
}

export interface TownshipCensus {
  name_en: string;
  name_local: string;
  population: SexCount;
  households: HouseholdSituation;
}

export interface DistrictCensus {
  name_en: string;
  name_local: string;
  population: SexCount;
  age_groups: CensusAgeGroup[];
  households: HouseholdSituation;
  townships: TownshipCensus[];
}

export interface CensusResponse {
  source: string;
  source_file: string;
  census_year: number;
  region_name_en: string;
  region_name_local: string;
  notes: string[];
  dwelling_types: DwellingTypeLabel[];
  population: { total: SexCount; urban: SexCount; rural: SexCount };
  age_groups: CensusAgeGroup[];
  households: HouseholdSituation & {
    urban_dwellings: DwellingCount;
    rural_dwellings: DwellingCount;
  };
  districts: DistrictCensus[];
}

export interface RouteStop {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
}

export interface RoutePlanRequest {
  origin: RouteStop;
  stops: RouteStop[];
  vehicle_profile: "car" | "truck" | "fly";
  service_minutes: number;
  return_to_origin: boolean;
}

export interface RouteWaypoint extends Coordinates {
  stop_id: string;
  name: string;
  arrival_time?: string | null;
  kind: string;
}

export interface RoutePlanResponse {
  plan_id: string;
  agency_id?: string | null;
  state: string;
  vehicle_profile: "car" | "truck" | "fly";
  distance_km?: number | null;
  duration?: string | null;
  duration_minutes?: number | null;
  waypoints: RouteWaypoint[];
  path: Coordinates[];
  unaffected_stop_ids: string[];
  disclaimer: string;
  assumptions: string[];
}

export interface SexCount {
  total: number;
  male: number;
  female: number;
}

export interface CensusAgeGroup {
  label: string;
  min_age: number;
  max_age: number | null;
  total: SexCount;
  urban: SexCount;
  rural: SexCount;
}

export interface HouseholdSizeBucket {
  size: string;
  households: number;
}

export interface DwellingCount {
  total: number;
  apartment: number;
  brick: number;
  semi_brick: number;
  wooden: number;
  bamboo: number;
  hut: number;
  other: number;
}

export interface HouseholdSituation {
  total: number;
  by_size: HouseholdSizeBucket[];
  by_dwelling: DwellingCount;
}

export interface DwellingTypeLabel {
  key: keyof Omit<DwellingCount, "total">;
  name_local: string;
  name_en: string;
}

export interface TownshipCensus {
  name_en: string;
  name_local: string;
  population: SexCount;
  households: HouseholdSituation;
}

export interface DistrictCensus {
  name_en: string;
  name_local: string;
  population: SexCount;
  age_groups: CensusAgeGroup[];
  households: HouseholdSituation;
  townships: TownshipCensus[];
}

export interface CensusResponse {
  source: string;
  source_file: string;
  census_year: number;
  region_name_en: string;
  region_name_local: string;
  notes: string[];
  dwelling_types: DwellingTypeLabel[];
  population: { total: SexCount; urban: SexCount; rural: SexCount };
  age_groups: CensusAgeGroup[];
  households: HouseholdSituation & {
    urban_dwellings: DwellingCount;
    rural_dwellings: DwellingCount;
  };
  districts: DistrictCensus[];
}

export interface HelpBriefResponse {
  source: string;
  disclaimer: string;
  recorded_flood_days: number;
  recorded_households: number;
  recorded_affected_people: number;
  townships_with_impact: number;
  highest_impacts: FloodHistoryRecord[];
}

export interface InventoryDetectionTrack {
  item_code: string;
  track_id: string;
  confidence: number;
}

export interface InventoryDetection {
  frames_processed?: number;
  tracks?: InventoryDetectionTrack[];
}

export interface InventoryDetectionConfirm {
  category_code: string;
  source: "image" | "video";
  items: InventoryDetectionItem[];
  tracks?: InventoryDetectionTrack[];
}

export interface AllocationStoreStatus {
  id: number;
  region: "east" | "west";
  name: string;
  latitude: number;
  longitude: number;
  verified_at: string | null;
  verification_note?: string | null;
}

export interface AllocationBlockedSegment {
  from_id: string;
  to_id: string;
  path: Coordinates[];
}

export interface AllocationPlanHistoryItem {
  plan_id: string;
  status: "draft" | "confirmed";
  created_at: string;
  prediction_run_id: number | null;
  planning_date: string | null;
}

export interface AllocationConfirmResult {
  plan_id: string;
  status: "draft" | "confirmed";
  prediction_run_id: number | null;
}

export interface FloodDrivers {
  rain: string;
  discharge: string;
  floodplain_or_river_distance: string;
}

export interface RegionForecastScore {
  township_id: string;
  township_name: string;
  district_id: string;
  latitude: number | null;
  longitude: number | null;
  lead_days: number;
  target_date: string;
  flood_probability: number | null;
  risk_band: "low" | "moderate" | "high" | "very_high" | "unknown";
  probability_risk_level: RiskLevel | null;
  risk_level: RiskLevel | "unknown";
  rainfall_mm: number | null;
  horizon_3d?: number | null;
  horizon_7d?: number | null;
  discharge_m3_s: number | null;
  static_hazard: number | null;
  early_warning: boolean;
  warning_reason: string | null;
  warning_level: "high" | "severe" | null;
  drivers: FloodDrivers;
  data_status: "model_estimate" | "unavailable" | "insufficient_features";
}

export interface RegionForecastResponse {
  as_of: string;
  run_id: number | null;
  model_version: string;
  feature_version: string;
  disclaimer: string;
  cached: boolean;
  labels_found: boolean;
  label_file: string | null;
  missing_inputs: string[];
  scores: RegionForecastScore[];
}
