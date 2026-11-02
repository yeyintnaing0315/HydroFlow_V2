from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    observations: Mapped[list["Observation"]] = relationship(cascade="all, delete-orphan")
    alerts: Mapped[list["Alert"]] = relationship(cascade="all, delete-orphan")


class HistoricalDay(Base):
    """Daily weather collected from the live history API and kept for the prediction page."""

    __tablename__ = "historical_days"
    __table_args__ = (
        UniqueConstraint("location_key", "observed_on", name="uq_historical_location_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_key: Mapped[str] = mapped_column(String(160), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    observed_on: Mapped[date] = mapped_column(Date, index=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    relative_humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_m_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="nasa-power")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (
        UniqueConstraint("location_id", "observed_at", "source", name="uq_observation_source_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(40))
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    discharge_m3_s: Mapped[float | None] = mapped_column(Float, nullable=True)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint("location_id", "issued_at", "level", name="uq_alert_location_time_level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    level: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(80), default="hydroflow-academic")


class DataSource(Base):
    """A provider or licensed dataset, including currently unavailable sources."""

    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    kind: Mapped[str] = mapped_column(String(40))
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    license_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    license_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attribution: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    unavailable_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint("source_id", "version", name="uq_dataset_source_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    version: Mapped[str] = mapped_column(String(80))
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class AdminArea(Base):
    __tablename__ = "admin_areas"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "source_code", name="uq_admin_dataset_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("admin_areas.id"), nullable=True, index=True)
    source_code: Mapped[str] = mapped_column(String(80), index=True)
    level: Mapped[int] = mapped_column(Integer, index=True)
    area_type: Mapped[str] = mapped_column(String(40))
    name_en: Mapped[str] = mapped_column(String(160), index=True)
    name_local: Mapped[str | None] = mapped_column(String(200), nullable=True)
    centroid_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    centroid_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    geometry_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    area_sq_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_status: Mapped[str] = mapped_column(String(40), default="complete")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)


class AdminAlias(Base):
    __tablename__ = "admin_aliases"
    __table_args__ = (
        UniqueConstraint("namespace", "alias", name="uq_admin_alias_namespace"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_area_id: Mapped[int] = mapped_column(ForeignKey("admin_areas.id"), index=True)
    namespace: Mapped[str] = mapped_column(String(60))
    alias: Mapped[str] = mapped_column(String(160), index=True)


class Settlement(Base):
    __tablename__ = "settlements"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "source_code", name="uq_settlement_dataset_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_version_id: Mapped[int] = mapped_column(ForeignKey("dataset_versions.id"), index=True)
    admin_area_id: Mapped[int | None] = mapped_column(ForeignKey("admin_areas.id"), nullable=True, index=True)
    source_code: Mapped[str] = mapped_column(String(80), index=True)
    name_en: Mapped[str] = mapped_column(String(160), index=True)
    name_local: Mapped[str | None] = mapped_column(String(200), nullable=True)
    settlement_type: Mapped[str] = mapped_column(String(40))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    verification_status: Mapped[str] = mapped_column(String(60), default="source_verified")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ProviderObservation(Base):
    __tablename__ = "provider_observations"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "variable",
            "location_key",
            "valid_at",
            name="uq_provider_observation",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    admin_area_id: Mapped[int | None] = mapped_column(ForeignKey("admin_areas.id"), nullable=True, index=True)
    location_key: Mapped[str] = mapped_column(String(160), index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    variable: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(40))
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    quality: Mapped[str] = mapped_column(String(40), default="unknown")
    missing: Mapped[bool] = mapped_column(Boolean, default=False)
    coverage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class OfficialWarning(Base):
    __tablename__ = "official_warnings"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_warning_source_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(160))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    severity: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), default="actual")
    message: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    coverage_json: Mapped[dict] = mapped_column(JSON, default=dict)


class InundationProduct(Base):
    __tablename__ = "inundation_products"
    __table_args__ = (
        UniqueConstraint("source_id", "external_id", name="uq_inundation_source_external"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(160))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    geometry_json: Mapped[dict] = mapped_column(JSON)
    quality: Mapped[str] = mapped_column(String(80), default="unvalidated")
    affected_population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    population_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ExposureSummary(Base):
    __tablename__ = "exposure_summaries"
    __table_args__ = (
        UniqueConstraint(
            "inundation_product_id",
            "admin_area_id",
            "population_source",
            name="uq_exposure_product_area_source",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    inundation_product_id: Mapped[int] = mapped_column(
        ForeignKey("inundation_products.id"), index=True
    )
    admin_area_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_areas.id"), nullable=True, index=True
    )
    population_source: Mapped[str] = mapped_column(String(160))
    exposed_population: Mapped[int] = mapped_column(Integer)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    method: Mapped[str] = mapped_column(Text)
    uncertainty_json: Mapped[dict] = mapped_column(JSON, default=dict)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    model_kind: Mapped[str] = mapped_column(String(60))
    artifact_uri: Mapped[str | None] = mapped_column(String(500), nullable=True)
    artifact_checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_status: Mapped[str] = mapped_column(String(60), default="unvalidated")
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    feature_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class JobRun(Base):
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    job_name: Mapped[str] = mapped_column(String(100), index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    freshness_json: Mapped[dict] = mapped_column(JSON, default=dict)
    coverage_json: Mapped[dict] = mapped_column(JSON, default=dict)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class RiskResult(Base):
    __tablename__ = "risk_results"
    __table_args__ = (
        UniqueConstraint(
            "job_run_id",
            "admin_area_id",
            "valid_at",
            "evidence_type",
            name="uq_risk_run_area_valid_evidence",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    job_run_id: Mapped[int] = mapped_column(ForeignKey("job_runs.id"), index=True)
    admin_area_id: Mapped[int | None] = mapped_column(ForeignKey("admin_areas.id"), nullable=True, index=True)
    valid_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    forecast_horizon_hours: Mapped[int] = mapped_column(Integer)
    evidence_type: Mapped[str] = mapped_column(String(40), index=True)
    risk_level: Mapped[str] = mapped_column(String(30))
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    model_version_id: Mapped[int | None] = mapped_column(ForeignKey("model_versions.id"), nullable=True)
    input_freshness_json: Mapped[dict] = mapped_column(JSON, default=dict)
    supporting_evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    uncertainty_json: Mapped[dict] = mapped_column(JSON, default=dict)


class InventoryCategory(Base):
    """Shared class list. Stock quantities live on stock_balances, one row per store."""

    __tablename__ = "inventory_categories"
    __table_args__ = (
        CheckConstraint(
            "entry_mode IN ('scan_or_manual', 'manual_only')",
            name="ck_inventory_category_entry_mode",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    entry_mode: Mapped[str] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer)
    item_types: Mapped[list["InventoryItemType"]] = relationship(
        back_populates="category",
        cascade="all, delete-orphan",
    )


class InventoryItemType(Base):
    __tablename__ = "inventory_item_types"
    __table_args__ = (
        UniqueConstraint("category_id", "code", name="uq_inventory_item_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("inventory_categories.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    unit: Mapped[str] = mapped_column(String(20))
    sort_order: Mapped[int] = mapped_column(Integer)
    category: Mapped[InventoryCategory] = relationship(back_populates="item_types")


class InventoryImage(Base):
    """One reference photo. confirmed_quantity is not a stock balance."""

    __tablename__ = "inventory_images"
    __table_args__ = (
        CheckConstraint(
            "(category_code IS NULL AND item_code IS NULL) OR (category_code IS NOT NULL AND item_code IS NOT NULL)",
            name="ck_inventory_image_class_pair",
        ),
        CheckConstraint("confirmed_quantity >= 0", name="ck_inventory_image_quantity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    relative_path: Mapped[str] = mapped_column(String(500))
    category_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    item_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    confirmed_quantity: Mapped[float] = mapped_column(
        Numeric(14, 2),
        default=0,
        server_default=text("0"),
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Store(Base):
    """A relief depot. East and west each have one seeded store."""

    __tablename__ = "stores"
    __table_args__ = (
        CheckConstraint("region IN ('east', 'west')", name="ck_store_region"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region: Mapped[str] = mapped_column(String(10), index=True)
    name: Mapped[str] = mapped_column(String(120))
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class StockBalance(Base):
    """On-hand quantity for one store, category, and optional item."""

    __tablename__ = "stock_balances"
    __table_args__ = (
        CheckConstraint("quantity >= 0", name="ck_stock_balance_nonnegative"),
        CheckConstraint(
            "(category_code <> 'fund') OR (item_code IS NULL)",
            name="ck_stock_fund_has_no_subclass",
        ),
        CheckConstraint(
            "(category_code = 'fund') OR (item_code IS NOT NULL)",
            name="ck_stock_subclass_required",
        ),
        Index(
            "uq_stock_balance_item",
            "store_id",
            "category_code",
            "item_code",
            unique=True,
            sqlite_where=text("item_code IS NOT NULL"),
            postgresql_where=text("item_code IS NOT NULL"),
        ),
        Index(
            "uq_stock_balance_fund",
            "store_id",
            "category_code",
            unique=True,
            sqlite_where=text("item_code IS NULL"),
            postgresql_where=text("item_code IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), index=True)
    item_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    quantity: Mapped[float] = mapped_column(Numeric(14, 2), default=0)
    unit: Mapped[str] = mapped_column(String(20))


class TownshipStaticFeatures(Base):
    """One current static-hazard row per township. Extra variables stay in features."""

    __tablename__ = "township_static_features"
    __table_args__ = (
        UniqueConstraint("township_id", name="uq_township_static_features_township"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    township_id: Mapped[str] = mapped_column(String(80), index=True)
    hand_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    jrc_rp10_depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    jrc_rp50_depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    jrc_rp100_depth_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    jrc_rp10_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    jrc_rp50_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    jrc_rp100_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    landcover_water_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    landcover_wetland_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    landcover_cropland_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    landcover_builtup_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    basin_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    feature_version: Mapped[str] = mapped_column(String(80))
    features: Mapped[dict] = mapped_column(JSON, default=dict)


class PredictionRun(Base):
    """One saved scoring pass. Forecast rows point at this run."""

    __tablename__ = "prediction_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    as_of: Mapped[date] = mapped_column(Date, index=True)
    model_version: Mapped[str] = mapped_column(String(120))
    feature_version: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    status: Mapped[str] = mapped_column(String(30), index=True)


class TownshipForecast(Base):
    __tablename__ = "township_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "township_id",
            "target_date",
            name="uq_forecast_run_township_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="CASCADE"),
        index=True,
    )
    township_id: Mapped[str] = mapped_column(String(80), index=True)
    target_date: Mapped[date] = mapped_column(Date, index=True)
    lead_days: Mapped[int] = mapped_column(Integer)
    probability: Mapped[float] = mapped_column(Float)
    risk_band: Mapped[str] = mapped_column(String(30))
    rainfall_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    discharge_m3_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    static_hazard: Mapped[float | None] = mapped_column(Float, nullable=True)
    warning_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    feature_version: Mapped[str] = mapped_column(String(80))
    features: Mapped[dict] = mapped_column(JSON, default=dict)


class FloodLabel(Base):
    """Observed relief history. Never written by a forecast."""

    __tablename__ = "flood_labels"
    __table_args__ = (
        UniqueConstraint("township_id", "observed_date", name="uq_flood_label_township_day"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    township_id: Mapped[str] = mapped_column(String(80), index=True)
    observed_date: Mapped[date] = mapped_column(Date, index=True)
    observed: Mapped[bool] = mapped_column(Boolean)
    affected_people: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(120))


class AllocationPlan(Base):
    __tablename__ = "allocation_plans"
    __table_args__ = (
        CheckConstraint("status IN ('draft', 'confirmed')", name="ck_allocation_plan_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    prediction_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("prediction_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    plan_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AllocationLine(Base):
    __tablename__ = "allocation_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("allocation_plans.id", ondelete="CASCADE"),
        index=True,
    )
    township_id: Mapped[str] = mapped_column(String(80), index=True)
    category_code: Mapped[str] = mapped_column(String(40))
    item_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    requested: Mapped[float] = mapped_column(Numeric(14, 2))
    allocated: Mapped[float] = mapped_column(Numeric(14, 2))
    priority: Mapped[str] = mapped_column(String(20))


class DetectionSession(Base):
    __tablename__ = "detection_sessions"
    __table_args__ = (
        CheckConstraint("source IN ('image', 'video')", name="ck_detection_session_source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    source: Mapped[str] = mapped_column(String(20))
    category_code: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DetectionObject(Base):
    __tablename__ = "detection_objects"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("detection_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    item_code: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[float] = mapped_column(Numeric(14, 2))
    mean_confidence: Mapped[float] = mapped_column(Float)
    track_id: Mapped[str | None] = mapped_column(String(80), nullable=True)


class StockMovement(Base):
    """A receipt or issue. It may point at an allocation line or a detection session."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_movement_quantity"),
        CheckConstraint("direction IN ('in', 'out')", name="ck_stock_movement_direction"),
        CheckConstraint(
            "entry_mode IN ('manual', 'scan')",
            name="ck_stock_movement_entry_mode",
        ),
        CheckConstraint(
            "(category_code <> 'fund') OR (entry_mode = 'manual' AND item_code IS NULL)",
            name="ck_stock_fund_manual_only",
        ),
        CheckConstraint(
            "(category_code = 'fund') OR (item_code IS NOT NULL)",
            name="ck_stock_movement_subclass_required",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), index=True)
    item_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    direction: Mapped[str] = mapped_column(String(10))
    entry_mode: Mapped[str] = mapped_column(String(20))
    quantity: Mapped[float] = mapped_column(Numeric(14, 2))
    allocation_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("allocation_lines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    detection_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("detection_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DeliveryRoute(Base):
    """Saved path for one plan and depot. geometry is GeoJSON text, not a PostGIS type."""

    __tablename__ = "delivery_routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("allocation_plans.id", ondelete="CASCADE"),
        index=True,
    )
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), index=True)
    label: Mapped[str] = mapped_column(String(80))
    routing_method: Mapped[str] = mapped_column(String(40))
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    blocked_segments: Mapped[list] = mapped_column(JSON, default=list)
    geometry: Mapped[str | None] = mapped_column(Text, nullable=True)


class RouteStop(Base):
    __tablename__ = "route_stops"
    __table_args__ = (
        UniqueConstraint("route_id", "seq", name="uq_route_stop_seq"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    route_id: Mapped[int] = mapped_column(
        ForeignKey("delivery_routes.id", ondelete="CASCADE"),
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer)
    township_id: Mapped[str] = mapped_column(String(80))


class TownshipRouteOption(Base):
    """Alternative depot-to-township roads saved for one draft or confirmed plan."""

    __tablename__ = "township_route_options"
    __table_args__ = (
        UniqueConstraint("plan_id", "township_id", "option_index", name="uq_township_route_option"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("allocation_plans.id", ondelete="CASCADE"),
        index=True,
    )
    township_id: Mapped[str] = mapped_column(String(80), index=True)
    option_index: Mapped[int] = mapped_column(Integer)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    recommended: Mapped[bool] = mapped_column(Boolean, default=False)
    routing_method: Mapped[str] = mapped_column(String(40))
    flood_exposure: Mapped[str] = mapped_column(String(20))
    distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    discharge_m3_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    blocked_segments: Mapped[list] = mapped_column(JSON, default=list)
    geometry: Mapped[str | None] = mapped_column(Text, nullable=True)
