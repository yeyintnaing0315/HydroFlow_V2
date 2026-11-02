from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Coordinates(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class PredictRequest(Coordinates):
    date: date
    township_id: str = Field(min_length=1, max_length=80)
    township_name_en: str | None = Field(default=None, max_length=120)


class PredictResponse(BaseModel):
    flood_probability: float = Field(ge=0, le=1)
    predicted_flood: bool
    threshold: float = Field(ge=0, le=1)
    model_version: str
    alert_recorded: bool
    evidence_type: Literal["model_prediction"] = "model_prediction"
    probability_status: Literal["uncalibrated_academic_score"] = "uncalibrated_academic_score"
    uncertainty: str = (
        "Not calibrated and not validated as a lead-time forecast; do not interpret operationally."
    )


class RiskResponse(BaseModel):
    score: float
    level: Literal["low", "moderate", "high", "severe"]
    label: Literal["academic prototype; not an operational warning"] = (
        "academic prototype; not an operational warning"
    )


class ForecastPoint(BaseModel):
    timestamp: datetime
    precipitation_mm: float | None = None
    temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    wind_speed_m_s: float | None = None
    discharge_m3_s: float | None = None


class ForecastResponse(Coordinates):
    points: list[ForecastPoint]


class AlertCreate(BaseModel):
    location_id: int
    issued_at: datetime
    level: Literal["low", "moderate", "high", "severe"]
    message: str = Field(min_length=1, max_length=500)


class AlertResponse(AlertCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str


class HistoricalPoint(BaseModel):
    date: date
    precipitation_mm: float | None = None
    temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    wind_speed_m_s: float | None = None


class HistoricalResponse(Coordinates):
    points: list[HistoricalPoint]


class FloodHistoryRecord(BaseModel):
    date: date
    township_id: str
    township: str
    latitude: float
    longitude: float
    households: int | None = None
    affected_people: int | None = None
    impact_severity: Literal["none", "low", "moderate", "high", "severe"]


class OutlookDay(BaseModel):
    date: date
    precipitation_mm: float
    discharge_m3_s: float
    temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    wind_speed_m_s: float | None = None
    rainfall_7d_mm: float | None = None
    rainfall_30d_mm: float | None = None
    flood_probability: float = Field(ge=0, le=1)
    predicted_flood: bool
    risk_score: float
    risk_level: Literal["low", "moderate", "high", "severe"]
    alert_recorded: bool
    forecast_horizon_hours: int = Field(ge=0)
    evidence_type: Literal["model_prediction"] = "model_prediction"
    probability_status: Literal["uncalibrated_academic_score"] = "uncalibrated_academic_score"
    input_freshness: dict[str, str | None] = Field(default_factory=dict)
    uncertainty: str = (
        "Uncalibrated academic score for flood in the next 3 days. Not an official warning."
    )


class OutlookResponse(BaseModel):
    township_id: str
    source: str = "Open-Meteo rainfall, NASA POWER meteorology, and GloFAS discharge"
    model_version: str
    in_training_set: bool = False
    days: list[OutlookDay]


class PredictionTimelineRequest(PredictRequest):
    as_of: date | None = None


class PredictionTimelineDay(BaseModel):
    date: date
    period_type: Literal["historical", "current", "forecast"]
    flood_probability: float | None = Field(default=None, ge=0, le=1)
    predicted_flood: bool | None = None
    probability_risk_level: Literal["low", "moderate", "high", "severe"] | None = None
    risk_level: Literal["low", "moderate", "high", "severe", "unknown"] = "unknown"
    hydrology_risk_score: float | None = None
    hydrology_risk_level: Literal["low", "moderate", "high", "severe"] | None = None
    rainfall_mm: float | None = None
    discharge_m3_s: float | None = None
    temperature_c: float | None = None
    relative_humidity_pct: float | None = None
    wind_speed_m_s: float | None = None
    rainfall_7d_mm: float | None = None
    impact_level: Literal["none", "low", "moderate", "high", "severe", "unknown"] = "unknown"
    potentially_exposed_population: int | None = None
    potentially_affected_population: int | None = None
    observed_flood: bool | None = None
    recorded_affected_people: int | None = None
    data_status: Literal["model_estimate", "observed_impact", "unavailable", "insufficient_features"]
    evidence_type: Literal["model_prediction", "archive_reference", "none"] = "none"
    probability_status: Literal["uncalibrated_academic_score"] | None = None
    forecast_horizon_hours: int = Field(default=0, ge=0)
    input_freshness: dict[str, str | None] = Field(default_factory=dict)
    uncertainty: str = ""
    key_factors: list[str] = Field(default_factory=list)
    secondary_flood_probability: float | None = Field(default=None, ge=0, le=1)
    secondary_probability_risk_level: Literal["low", "moderate", "high", "severe"] | None = None


class PredictionTimelineResponse(BaseModel):
    township_id: str
    as_of: date
    timezone: str
    model_version: str
    secondary_model_version: str | None = None
    in_training_set: bool = False
    generated_at: datetime
    potentially_exposed_population: int | None = None
    disclaimer: str
    days: list[PredictionTimelineDay]


class TownshipMapScore(BaseModel):
    township_id: str
    township_name: str
    latitude: float | None = None
    longitude: float | None = None
    parent_id: int | None = None
    flood_probability: float | None = Field(default=None, ge=0, le=1)
    probability_risk_level: Literal["low", "moderate", "high", "severe"] | None = None
    secondary_flood_probability: float | None = Field(default=None, ge=0, le=1)
    secondary_probability_risk_level: Literal["low", "moderate", "high", "severe"] | None = None
    risk_level: Literal["low", "moderate", "high", "severe", "unknown"] = "unknown"
    rainfall_mm: float | None = None
    horizon_3d: float | None = Field(default=None, ge=0, le=1)
    horizon_7d: float | None = Field(default=None, ge=0, le=1)
    data_status: Literal["model_estimate", "unavailable", "insufficient_features"]


class PredictionMapScoresResponse(BaseModel):
    date: date
    model_version: str
    secondary_model_version: str | None = None
    cached: bool = False
    scores: list[TownshipMapScore]


class TownshipResponse(BaseModel):
    township_id: str
    township: str
    latitude: float
    longitude: float


class AdminTownship(BaseModel):
    id: str
    slug: str
    name_en: str
    name_local: str
    latitude: float
    longitude: float
    geometry: dict | None = None
    level: int = 3
    area_type: str = "township"
    coverage_status: str = "complete"


class AdminDistrict(AdminTownship):
    townships: list[AdminTownship]


class BagoAreasResponse(BaseModel):
    source: str
    dataset_version: str
    license: str
    coverage_note: str
    region_id: str
    region_name_en: Literal["Bago"] = "Bago"
    region_name_local: str
    latitude: float
    longitude: float
    geometry: dict | None = None
    districts: list[AdminDistrict]


class SourceStatusResponse(BaseModel):
    key: str
    name: str
    kind: str
    enabled: bool
    unavailable_reason: str | None = None
    attribution: str
    license_name: str | None = None
    url: str


class AdminAreaResponse(BaseModel):
    id: str
    parent_id: str | None = None
    level: int
    area_type: str
    name_en: str
    name_local: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geometry: dict | None = None
    coverage_status: str


class AdminHierarchyResponse(BaseModel):
    source: str
    dataset_version: str
    license: str
    coverage_note: str
    areas: list[AdminAreaResponse]


class OfficialWarningResponse(BaseModel):
    id: int
    source: str
    external_id: str
    issued_at: datetime
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    severity: str
    status: str
    message: str
    source_url: str | None = None
    coverage: dict = Field(default_factory=dict)


class OfficialWarningImport(BaseModel):
    external_id: str = Field(min_length=1, max_length=160)
    issued_at: datetime
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    severity: str = Field(min_length=1, max_length=40)
    status: str = Field(default="actual", min_length=1, max_length=40)
    message: str = Field(min_length=1, max_length=10_000)
    source_url: str = Field(pattern=r"^https://", max_length=500)
    coverage: dict = Field(default_factory=dict, max_length=100)

    @field_validator("issued_at", "effective_at", "expires_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("warning datetimes must include a timezone")
        return value


class InundationProductResponse(BaseModel):
    id: int
    evidence_type: Literal["observed_inundation"] = "observed_inundation"
    observed_at: datetime
    retrieved_at: datetime
    geometry: dict
    quality: str
    affected_population: int | None = Field(default=None, ge=0)
    population_source: str | None = None
    metadata: dict = Field(default_factory=dict)


class SettlementResponse(BaseModel):
    id: int
    source_code: str
    admin_area_id: int | None = None
    name_en: str
    name_local: str | None = None
    settlement_type: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    verification_status: str
    note: Literal[
        "A settlement point does not imply that the settlement area is inundated."
    ]


class ExposureSummaryResponse(BaseModel):
    id: int
    inundation_product_id: int
    admin_area_id: int | None = None
    population_source: str
    exposed_population: int = Field(ge=0)
    calculated_at: datetime
    method: str
    uncertainty: dict = Field(default_factory=dict)


class RiskResultResponse(BaseModel):
    id: int
    admin_area_id: int | None = None
    admin_area_code: str | None = None
    admin_area_name: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    valid_at: datetime
    forecast_horizon_hours: int = Field(ge=0)
    evidence_type: Literal["heuristic_risk", "model_prediction"]
    risk_level: Literal["low", "moderate", "high", "severe"]
    risk_score: float | None = Field(default=None, ge=0, le=100)
    probability: float | None = Field(default=None, ge=0, le=1)
    input_freshness: dict = Field(default_factory=dict)
    supporting_evidence: dict = Field(default_factory=dict)
    uncertainty: dict = Field(default_factory=dict)


class JobRunResponse(BaseModel):
    id: int
    job_name: str
    scheduled_for: datetime
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    attempt: int
    model_version: str | None = None
    freshness: dict = Field(default_factory=dict)
    coverage: dict = Field(default_factory=dict)
    error: str | None = None


class FloodHistoryResponse(BaseModel):
    source: Literal["Bago relief records"] = "Bago relief records"
    disclaimer: Literal["Recorded impacts, not model predictions."] = (
        "Recorded impacts, not model predictions."
    )
    matched_records: int
    records: list[FloodHistoryRecord]


class HelpDay(BaseModel):
    date: date
    help_probability: float = Field(ge=0, le=1)
    predicted_help: bool
    expected_affected_people: int = Field(ge=0)
    expected_households: int = Field(ge=0)
    affected_male: int | None = Field(default=None, ge=0)
    affected_female: int | None = Field(default=None, ge=0)
    impact_source: str | None = None
    assistance_priority: Literal["none", "low", "moderate", "high", "severe"]
    shelter_kits: int = Field(ge=0)
    food_rations_3d: int = Field(ge=0)
    drinking_water_liters_3d: int = Field(ge=0)


class HelpResponse(BaseModel):
    township_id: str
    source: Literal["Open-Meteo rainfall and GloFAS discharge"] = (
        "Open-Meteo rainfall and GloFAS discharge"
    )
    model_version: str
    disclaimer: Literal[
        "Academic planning aid. Not an operational humanitarian response plan."
    ] = "Academic planning aid. Not an operational humanitarian response plan."
    days: list[HelpDay]


class TopographyResponse(BaseModel):
    latitude: float
    longitude: float
    elevation_m: float
    dataset: str
    vertical_datum: Literal["EGM2008"] = "EGM2008"
    vertical_datum_epsg: str
    unit: Literal["Meters"] = "Meters"
    source: Literal["OpenTopography Copernicus GLO-30"] = "OpenTopography Copernicus GLO-30"
    note: Literal[
        "Surface elevation at the requested point. The flood model does not use this value."
    ] = "Surface elevation at the requested point. The flood model does not use this value."


class RouteStop(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class RoutePlanRequest(BaseModel):
    origin: RouteStop
    stops: list[RouteStop] = Field(min_length=1, max_length=12)
    vehicle_profile: Literal["car", "truck", "fly"] = "car"
    service_minutes: int = Field(default=15, ge=0, le=180)
    return_to_origin: bool = True


class RouteWaypoint(BaseModel):
    stop_id: str
    name: str
    latitude: float
    longitude: float
    arrival_time: datetime | None = None
    kind: str


class RoutePlanResponse(BaseModel):
    plan_id: str
    agency_id: str | None = None
    state: str
    vehicle_profile: Literal["car", "truck", "fly"]
    distance_km: float | None = None
    duration: str | None = None
    duration_minutes: float | None = None
    waypoints: list[RouteWaypoint]
    path: list[Coordinates]
    unaffected_stop_ids: list[str]
    disclaimer: Literal[
        "Academic route illustration from Kardinal. Not an operational dispatch plan."
    ] = "Academic route illustration from Kardinal. Not an operational dispatch plan."
    assumptions: list[str]


class SexCount(BaseModel):
    total: int = Field(ge=0)
    male: int = Field(ge=0)
    female: int = Field(ge=0)


class ResidencePopulation(BaseModel):
    total: SexCount
    urban: SexCount
    rural: SexCount


class AgeGroup(BaseModel):
    label: str
    min_age: int = Field(ge=0)
    max_age: int | None = None
    total: SexCount
    urban: SexCount
    rural: SexCount


class HouseholdSizeBucket(BaseModel):
    size: str
    households: int = Field(ge=0)


class DwellingCount(BaseModel):
    total: int = Field(ge=0)
    apartment: int = Field(ge=0)
    brick: int = Field(ge=0)
    semi_brick: int = Field(ge=0)
    wooden: int = Field(ge=0)
    bamboo: int = Field(ge=0)
    hut: int = Field(ge=0)
    other: int = Field(ge=0)


class HouseholdSituation(BaseModel):
    total: int = Field(ge=0)
    by_size: list[HouseholdSizeBucket]
    by_dwelling: DwellingCount


class DwellingType(BaseModel):
    key: str
    name_local: str
    name_en: str


class TownshipCensus(BaseModel):
    name_en: str
    name_local: str
    population: SexCount
    households: HouseholdSituation


class DistrictCensus(BaseModel):
    name_en: str
    name_local: str
    population: SexCount
    age_groups: list[AgeGroup]
    households: HouseholdSituation
    townships: list[TownshipCensus]


class RegionHouseholds(HouseholdSituation):
    urban_dwellings: DwellingCount
    rural_dwellings: DwellingCount


class CensusResponse(BaseModel):
    source: Literal["2024 Population and Housing Census, Bago Region tables"] = (
        "2024 Population and Housing Census, Bago Region tables"
    )
    source_file: str
    census_year: Literal[2024] = 2024
    region_name_en: Literal["Bago"] = "Bago"
    region_name_local: str
    notes: list[str]
    dwelling_types: list[DwellingType]
    population: ResidencePopulation
    age_groups: list[AgeGroup]
    households: RegionHouseholds
    districts: list[DistrictCensus]


class HelpBriefResponse(BaseModel):
    source: Literal["Bago relief records"] = "Bago relief records"
    disclaimer: Literal["Recorded impacts, not flood-help model predictions."] = (
        "Recorded impacts, not flood-help model predictions."
    )
    recorded_flood_days: int
    recorded_households: int
    recorded_affected_people: int
    townships_with_impact: int
    highest_impacts: list[FloodHistoryRecord]


FloodCaseSource = Literal["recorded", "model"]
FloodCaseLevel = Literal["high", "severe"]
FloodCaseView = Literal["events", "days"]


class FloodCaseItem(BaseModel):
    place: str
    township_id: str
    depot: str
    source: FloodCaseSource
    level: FloodCaseLevel
    start_date: date
    end_date: date
    peak_date: date
    peak_score: float | None = None
    households: int | None = None
    affected_people: int | None = None
    days: int = Field(ge=1)
    overlap: bool = False


class FloodCaseCounts(BaseModel):
    total: int = Field(ge=0)
    severe: int = Field(ge=0)
    high: int = Field(ge=0)
    recorded: int = Field(ge=0)
    model: int = Field(ge=0)
    overlap: int = Field(ge=0)


class FloodCaseYearCount(BaseModel):
    year: int
    count: int = Field(ge=0)


class FloodCaseCatalogResponse(BaseModel):
    source_file: str
    view: FloodCaseView
    disclaimer: str
    counts: FloodCaseCounts
    by_year: list[FloodCaseYearCount]
    events: list[FloodCaseItem]


AssistancePriorityLevel = Literal["none", "low", "moderate", "high", "severe"]


class DepotNetworkLeg(BaseModel):
    township_id: str
    depot_region: Literal["east", "west"]
    depot_latitude: float = Field(ge=-90, le=90)
    depot_longitude: float = Field(ge=-180, le=180)
    township_latitude: float = Field(ge=-90, le=90)
    township_longitude: float = Field(ge=-180, le=180)


class DepotNetworkRoute(BaseModel):
    township_id: str
    depot_region: Literal["east", "west"]
    path: list[Coordinates]
    distance_m: float | None = None
    routing_method: Literal["osrm_road", "straight_line_fallback"] = "straight_line_fallback"


class DepotNetworkRoutesRequest(BaseModel):
    legs: list[DepotNetworkLeg] = Field(default_factory=list, max_length=32)


class DepotNetworkRoutesResponse(BaseModel):
    routes: list[DepotNetworkRoute]
    disclaimer: str = "Road distances follow the public OSRM driving network when available."


class AllocationPlanRequest(BaseModel):
    date: date
    warehouse_region: Literal["east", "west", "auto"] = "auto"
    min_priority: AssistancePriorityLevel = "moderate"
    township_ids: list[str] | None = Field(default=None, max_length=40)
    include_all_high_severe: bool = True
    commit_inventory: bool = True
    vehicle_profile: Literal["car", "truck", "fly"] = "truck"


class AllocationLineItem(BaseModel):
    category_code: str
    item_code: str | None = None
    name: str
    unit: str
    requested: float = Field(ge=0)
    allocated: float = Field(ge=0)


class TownshipRouteOptionView(BaseModel):
    """One real depot-to-township corridor. Missing metrics stay null."""

    option_index: int = Field(ge=1, le=3)
    label: str
    path: list[Coordinates]
    distance_m: float | None = None
    duration_s: float | None = None
    routing_method: str
    flood_exposure: Literal["clear", "penalized", "blocked", "unknown"] = "unknown"
    blocked_segments: list[dict[str, object]] = Field(default_factory=list)
    rainfall_mm: float | None = None
    discharge_m3_s: float | None = None
    recommended: bool = False
    selected: bool = False


class AllocationTownshipRow(BaseModel):
    township_id: str
    township_name: str
    latitude: float
    longitude: float
    population: int = Field(ge=0)
    affected_male: int = Field(default=0, ge=0)
    affected_female: int = Field(default=0, ge=0)
    priority: AssistancePriorityLevel
    resources_label: str
    quantities_label: str
    line_items: list[AllocationLineItem]
    route_id: str
    depot_region: Literal["east", "west"] = "east"
    has_shortage: bool = False
    flood_probability: float | None = None
    risk_band: str | None = None
    rainfall_mm: float | None = None
    discharge_m3_s: float | None = None
    requested_total: float = Field(default=0, ge=0)
    allocated_total: float = Field(default=0, ge=0)
    route_options: list[TownshipRouteOptionView] = Field(default_factory=list)


class TownshipRouteComparison(BaseModel):
    plan_id: str
    township_id: str
    depot_region: Literal["east", "west"] = "east"
    alternatives: list[TownshipRouteOptionView] = Field(default_factory=list)
    alternatives_available: bool = False
    rainfall_mm: float | None = None
    discharge_m3_s: float | None = None
    flood_probability: float | None = None
    risk_band: str | None = None


class AllocationShortage(BaseModel):
    category_code: str
    item_code: str | None = None
    name: str
    unit: str
    requested: float = Field(ge=0)
    available: float = Field(ge=0)
    unmet: float = Field(ge=0)
    depot_region: Literal["east", "west"] = "east"


class AllocationWarehouse(BaseModel):
    id: str
    name: str
    region: Literal["east", "west"]
    latitude: float
    longitude: float


class AllocationRouteSummary(BaseModel):
    route_id: str
    stop_count: int = Field(ge=0)
    path: list[Coordinates]
    depot_region: Literal["east", "west"] = "east"
    routing_method: Literal["osrm_road", "straight_line_fallback"] = "straight_line_fallback"
    plan: RoutePlanResponse | None = None


class AllocationTotals(BaseModel):
    affected_population: int = Field(ge=0)
    available_stock_units: float | None = None
    resources_needed_units: float = Field(ge=0)


class AllocationPlanResponse(BaseModel):
    plan_id: str
    planning_date: date
    warehouse: AllocationWarehouse
    warehouses: list[AllocationWarehouse] = Field(default_factory=list)
    totals: AllocationTotals
    rows: list[AllocationTownshipRow]
    shortages: list[AllocationShortage]
    routes: list[AllocationRouteSummary]
    model_version: str
    disclaimer: Literal[
        "Academic allocation illustration. Not an operational dispatch plan."
    ] = "Academic allocation illustration. Not an operational dispatch plan."


class AllocationDispatchLine(BaseModel):
    category_code: str = Field(min_length=1, max_length=40)
    item_code: str | None = Field(default=None, max_length=40)
    quantity: float = Field(gt=0)
    destination: str | None = Field(default=None, max_length=160)


class AllocationDispatchRequest(BaseModel):
    warehouse_region: Literal["east", "west"]
    lines: list[AllocationDispatchLine] = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=300)
