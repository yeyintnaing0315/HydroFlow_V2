from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

REQUIRED_COLUMNS = {
    "date",
    "rainfall_mm",
    "river_discharge_m3s",
    "township_id",
    "township",
    "lat",
    "lng",
    "households",
    "affected_people",
    "flood",
}


class DataValidationError(ValueError):
    """Raised when source data violates a modelling invariant."""


@dataclass(frozen=True)
class ValidationReport:
    rows: int
    townships: int
    start_date: str
    end_date: str
    flood_rows: int
    non_flood_rows: int
    flood_rate: float
    townships_with_flood: int
    min_rows_per_township: int
    max_rows_per_township: int
    missing_impact_rows: int

    def as_dict(self) -> dict[str, int | float | str]:
        return self.__dict__.copy()


def validate_daily_data(data: pd.DataFrame) -> ValidationReport:
    missing = sorted(REQUIRED_COLUMNS - set(data.columns))
    if missing:
        raise DataValidationError(f"Missing required columns: {missing}")
    if data.empty:
        raise DataValidationError("Dataset is empty")

    dates = pd.to_datetime(data["date"], errors="coerce")
    if dates.isna().any():
        raise DataValidationError("date contains invalid or missing values")
    if data[["township_id", "rainfall_mm", "river_discharge_m3s", "lat", "lng", "flood"]].isna().any().any():
        raise DataValidationError("Required modelling fields contain missing values")
    if data.duplicated(["township_id", "date"]).any():
        raise DataValidationError("Duplicate township/date rows found")
    if not set(pd.unique(data["flood"])).issubset({0, 1}):
        raise DataValidationError("flood must contain binary 0/1 labels")
    if (data[["rainfall_mm", "river_discharge_m3s"]] < 0).any().any():
        raise DataValidationError("Rainfall and discharge must be non-negative")
    if not data["lat"].between(-90, 90).all() or not data["lng"].between(-180, 180).all():
        raise DataValidationError("Coordinates are outside valid ranges")

    impact_missing = data[list(("households", "affected_people"))].isna().all(axis=1)
    rows_by_township = data.groupby("township_id", sort=False).size()
    flood_by_township = data.groupby("township_id", sort=False)["flood"].sum()
    flood_rows = int(data["flood"].sum())
    return ValidationReport(
        rows=len(data),
        townships=int(data["township_id"].nunique()),
        start_date=dates.min().date().isoformat(),
        end_date=dates.max().date().isoformat(),
        flood_rows=flood_rows,
        non_flood_rows=int(len(data) - flood_rows),
        flood_rate=float(data["flood"].mean()),
        townships_with_flood=int((flood_by_township > 0).sum()),
        min_rows_per_township=int(rows_by_township.min()),
        max_rows_per_township=int(rows_by_township.max()),
        missing_impact_rows=int(impact_missing.sum()),
    )
