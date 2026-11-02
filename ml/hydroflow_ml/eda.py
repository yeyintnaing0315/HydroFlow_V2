from __future__ import annotations

import json

import pandas as pd

from .config import EDA_PATH
from .splits import chronological_split


def _flood_event_durations(data: pd.DataFrame) -> pd.Series:
    """Length, in consecutive calendar days, of each township flood run."""
    floods = data.loc[data["flood"].astype(int) == 1, ["township_id", "date"]].copy()
    if floods.empty:
        return pd.Series(dtype="int64")
    floods["date"] = pd.to_datetime(floods["date"])
    floods = floods.sort_values(["township_id", "date"], kind="stable")
    previous = floods.groupby("township_id", sort=False)["date"].shift(1)
    starts = previous.isna() | (floods["date"] - previous).dt.days.ne(1)
    event_ids = starts.groupby(floods["township_id"], sort=False).cumsum()
    return floods.groupby(["township_id", event_ids], sort=False).size()


def create_eda_summary(data: pd.DataFrame, destination=EDA_PATH) -> dict:
    dates = pd.to_datetime(data["date"])
    by_year = (
        data.assign(year=dates.dt.year)
        .groupby("year")["flood"]
        .agg(rows="size", flood_rows="sum", flood_rate="mean")
    )
    by_township = (
        data.groupby("township_id", sort=True)["flood"]
        .agg(rows="size", flood_rows="sum")
    )
    durations = _flood_event_durations(data)
    split = chronological_split(data)
    test_dates = dates[split == "test"]
    flood_rows = int(data["flood"].sum())
    summary = {
        "rows": int(len(data)),
        "date_range": [dates.min().date().isoformat(), dates.max().date().isoformat()],
        "townships": int(data["township_id"].nunique()),
        "flood_rows": flood_rows,
        "flood_rate": float(data["flood"].mean()),
        "missing_by_column": {key: int(value) for key, value in data.isna().sum().items()},
        "numeric_summary": json.loads(
            data[["rainfall_mm", "river_discharge_m3s"]]
            .describe(percentiles=[0.5, 0.9, 0.95, 0.99])
            .to_json()
        ),
        "labels_by_year": {
            str(year): {
                "rows": int(row["rows"]),
                "flood_rows": int(row["flood_rows"]),
                "flood_rate": float(row["flood_rate"]),
            }
            for year, row in by_year.iterrows()
        },
        "flood_event_duration": {
            "events": int(len(durations)),
            "min_days": int(durations.min()) if len(durations) else 0,
            "median_days": float(durations.median()) if len(durations) else 0.0,
            "max_days": int(durations.max()) if len(durations) else 0,
            "mean_days": float(durations.mean()) if len(durations) else 0.0,
        },
        "township_coverage": {
            "townships": int(len(by_township)),
            "townships_with_flood": int((by_township["flood_rows"] > 0).sum()),
            "flood_rows_by_township": {
                str(township): {
                    "rows": int(row["rows"]),
                    "flood_rows": int(row["flood_rows"]),
                }
                for township, row in by_township.iterrows()
            },
        },
        "positive_day_assessment": {
            "flood_rows": flood_rows,
            "test_block_flood_rows": int(data.loc[split == "test", "flood"].sum()),
            "test_block_start": test_dates.min().date().isoformat(),
            "test_block_end": test_dates.max().date().isoformat(),
            "note": (
                "Positives are rare. The chronological test block is the last 20% of "
                "dates and is counted here so that sparsity is visible before training."
            ),
        },
        "feature_target_timing": (
            "The flood label is the same calendar day as rainfall_mm and "
            "river_discharge_m3s. Those same-day values are contemporaneous with the "
            "label, not a forecast lead. Lag and rolling features use only the current "
            "row and earlier rows within the township."
        ),
        "leakage_note": (
            "households and affected_people describe observed impacts and are excluded "
            "from all predictive features."
        ),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary
