"""List days the flood map would color above low.

Uses the served gradient-boosting model and the same bands as the dashboard:
low under 25%, moderate under 50%, high under 75%, severe from 75%.
Map color and the prediction card both use that day's model probability.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HYDRO_DIR = ROOT / "data" / "external" / "hydro_merged"
MODEL_PATH = ROOT / "ml" / "models" / "bago_flood_model.joblib"
META_PATH = ROOT / "ml" / "models" / "bago_flood_model_metadata.json"
OUT_PATH = ROOT / "data" / "processed" / "map_flood_days.csv"

EAST_LAT, EAST_LNG = 17.335, 96.481
WEST_LAT, WEST_LNG = 18.817, 95.217
FEATURES = (
    "rainfall_1d_mm",
    "rainfall_3d_mm",
    "rainfall_7d_mm",
    "rainfall_14d_mm",
    "rainfall_30d_mm",
    "temperature_c",
    "relative_humidity_pct",
    "wind_speed_m_s",
    "latitude",
    "longitude",
    "day_of_year_sin",
    "day_of_year_cos",
    "discharge_lag_1d_m3s",
    "discharge_lag_3d_mean_m3s",
)
COLUMNS = (
    "place",
    "township_id",
    "depot",
    "map_level",
    "start_date",
    "end_date",
    "peak_date",
    "map_chance_pct",
    "day_chance_pct",
    "day_level",
    "rainfall_mm",
    "discharge_m3s",
    "days",
)
LEVEL_RANK = {"moderate": 1, "high": 2, "severe": 3}


def depot_for(latitude: float, longitude: float) -> str:
    if longitude >= 96.08:
        return "Bago (east)"
    if longitude <= 95.92:
        return "Pyay (west)"
    east = (latitude - EAST_LAT) ** 2 + (longitude - EAST_LNG) ** 2
    west = (latitude - WEST_LAT) ** 2 + (longitude - WEST_LNG) ** 2
    return "Bago (east)" if east <= west else "Pyay (west)"


def map_level(probability: float) -> str:
    if probability < 0.25:
        return "low"
    if probability < 0.50:
        return "moderate"
    if probability < 0.75:
        return "high"
    return "severe"


def strict_window_sum(ordinals: np.ndarray, values: np.ndarray, size: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if size <= 1:
        return values.astype(float)
    for index in range(size - 1, len(values)):
        if int(ordinals[index] - ordinals[index - size + 1]) != size - 1:
            continue
        window = values[index - size + 1 : index + 1]
        if np.isnan(window).any():
            continue
        out[index] = float(window.sum())
    return out


def lagged(ordinals: np.ndarray, values: np.ndarray, offset: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    for index in range(offset, len(values)):
        if int(ordinals[index] - ordinals[index - offset]) != offset:
            continue
        value = values[index - offset]
        if not np.isnan(value):
            out[index] = float(value)
    return out


def hydro_paths() -> list[Path]:
    chosen: dict[str, Path] = {}
    for path in sorted(HYDRO_DIR.glob("*.csv")):
        if path.stem.upper().startswith("MMR"):
            continue
        with path.open(newline="", encoding="utf-8") as handle:
            fields = set(csv.DictReader(handle).fieldnames or ())
        needed = {
            "latitude",
            "longitude",
            "temperature_c",
            "relative_humidity_pct",
            "wind_speed_m_s",
            "rainfall_mm",
            "river_discharge_m3s",
        }
        if not needed <= fields:
            continue
        chosen[path.stem] = path
    return [chosen[key] for key in sorted(chosen)]


def score_file(path: Path, model) -> pd.DataFrame:
    frame = pd.read_csv(
        path,
        usecols=[
            "date",
            "township_id",
            "township",
            "latitude",
            "longitude",
            "temperature_c",
            "relative_humidity_pct",
            "wind_speed_m_s",
            "rainfall_mm",
            "river_discharge_m3s",
        ],
        parse_dates=["date"],
    )
    frame = frame.dropna(subset=["date", "rainfall_mm", "river_discharge_m3s"]).sort_values("date")
    frame = frame.drop_duplicates("date", keep="last")
    if frame.empty:
        return frame
    ordinals = frame["date"].map(lambda item: item.toordinal()).to_numpy()
    rain = frame["rainfall_mm"].to_numpy(dtype=float)
    discharge = frame["river_discharge_m3s"].to_numpy(dtype=float)
    lag1 = lagged(ordinals, discharge, 1)
    lag2 = lagged(ordinals, discharge, 2)
    lag3 = lagged(ordinals, discharge, 3)
    day_number = frame["date"].dt.dayofyear.to_numpy()
    built = pd.DataFrame(
        {
            "date": frame["date"].dt.date,
            "place": frame["township"].fillna(path.stem).astype(str),
            "township_id": frame["township_id"].fillna(path.stem).astype(str),
            "latitude": frame["latitude"].to_numpy(dtype=float),
            "longitude": frame["longitude"].to_numpy(dtype=float),
            "rainfall_mm": rain,
            "discharge_m3s": discharge,
            "rainfall_1d_mm": rain,
            "rainfall_3d_mm": strict_window_sum(ordinals, rain, 3),
            "rainfall_7d_mm": strict_window_sum(ordinals, rain, 7),
            "rainfall_14d_mm": strict_window_sum(ordinals, rain, 14),
            "rainfall_30d_mm": strict_window_sum(ordinals, rain, 30),
            "temperature_c": frame["temperature_c"].to_numpy(dtype=float),
            "relative_humidity_pct": frame["relative_humidity_pct"].to_numpy(dtype=float),
            "wind_speed_m_s": frame["wind_speed_m_s"].to_numpy(dtype=float),
            "day_of_year_sin": np.sin(2 * math.pi * day_number / 365.25),
            "day_of_year_cos": np.cos(2 * math.pi * day_number / 365.25),
            "discharge_lag_1d_m3s": np.where(np.isnan(lag1), np.roll(discharge, 1), lag1),
            "discharge_lag_3d_mean_m3s": (lag1 + lag2 + lag3) / 3.0,
        }
    )
    built.loc[built.index[0], "discharge_lag_1d_m3s"] = np.nan
    ready = built.dropna(subset=list(FEATURES)).copy()
    if ready.empty:
        return ready
    probabilities = model.predict_proba(ready.loc[:, FEATURES])[:, 1]
    ready["day_probability"] = probabilities
    return ready


def horizon_chance(by_day: dict[date, float], day: date) -> float:
    remain = 1.0
    known = False
    for offset in range(4):
        value = by_day.get(day + timedelta(days=offset))
        if value is None:
            continue
        known = True
        remain *= 1.0 - min(1.0, max(0.0, float(value)))
    if not known:
        return 0.0
    return 1.0 - remain


def collapse(days: list[dict[str, object]]) -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    run: list[dict[str, object]] = []

    def flush() -> None:
        if not run:
            return
        peak = max(run, key=lambda item: (float(item["map_probability"]), -item["date"].toordinal()))
        cases.append(
            {
                "place": str(peak["place"]),
                "township_id": str(peak["township_id"]),
                "depot": str(peak["depot"]),
                "map_level": str(peak["map_level"]),
                "start_date": run[0]["date"].isoformat(),
                "end_date": run[-1]["date"].isoformat(),
                "peak_date": peak["date"].isoformat(),
                "map_chance_pct": f"{float(peak['map_probability']) * 100:.1f}",
                "day_chance_pct": f"{float(peak['day_probability']) * 100:.1f}",
                "day_level": str(peak["day_level"]),
                "rainfall_mm": f"{float(peak['rainfall_mm']):.1f}",
                "discharge_m3s": f"{float(peak['discharge_m3s']):.1f}",
                "days": str(len(run)),
            }
        )

    for item in days:
        if run and (
            item["township_id"] != run[-1]["township_id"]
            or item["date"] != run[-1]["date"] + timedelta(days=1)
        ):
            flush()
            run = []
        run.append(item)
    flush()
    return cases


def model_catalog_cases(
    model,
    *,
    levels: frozenset[str] = frozenset({"high", "severe"}),
) -> list[dict[str, str]]:
    """High/severe spells from the served model (same bands as the dashboard map)."""
    scored: list[pd.DataFrame] = []
    for path in hydro_paths():
        ready = score_file(path, model)
        if not ready.empty:
            scored.append(ready)
    if not scored:
        return []
    flood_days: list[dict[str, object]] = []
    for row in pd.concat(scored, ignore_index=True).itertuples(index=False):
        chance = float(row.day_probability)
        level = map_level(chance)
        if level not in levels:
            continue
        flood_days.append(
            {
                "place": row.place,
                "township_id": row.township_id,
                "depot": depot_for(float(row.latitude), float(row.longitude)),
                "date": row.date,
                "map_level": level,
                "map_probability": chance,
            }
        )
    flood_days.sort(key=lambda item: (item["township_id"], item["date"]))
    catalog: list[dict[str, str]] = []
    for spell in collapse(flood_days):
        catalog.append(
            {
                "place": spell["place"],
                "township_id": spell["township_id"],
                "depot": spell["depot"],
                "source": "model",
                "level": spell["map_level"],
                "start_date": spell["start_date"],
                "end_date": spell["end_date"],
                "peak_date": spell["peak_date"],
                "peak_score": f'{float(spell["map_chance_pct"]):.1f}',
                "households": "",
                "affected_people": "",
                "days": spell["days"],
                "overlap": "",
            }
        )
    return catalog


def main() -> None:
    metadata = json.loads(META_PATH.read_text(encoding="utf-8"))
    listed = [str(name) for name in metadata.get("features") or []]
    if listed and tuple(listed) != FEATURES:
        raise SystemExit(f"model features changed: {listed}")
    model = joblib.load(MODEL_PATH)
    scored: list[pd.DataFrame] = []
    for path in hydro_paths():
        ready = score_file(path, model)
        if not ready.empty:
            scored.append(ready)
    if not scored:
        raise SystemExit("no scorable station days")
    all_days = pd.concat(scored, ignore_index=True)
    flood_days: list[dict[str, object]] = []
    for row in all_days.itertuples(index=False):
        chance = float(row.day_probability)
        level = map_level(chance)
        if level == "low":
            continue
        flood_days.append(
            {
                "place": row.place,
                "township_id": row.township_id,
                "depot": depot_for(float(row.latitude), float(row.longitude)),
                "date": row.date,
                "map_level": level,
                "map_probability": chance,
                "day_probability": chance,
                "day_level": level,
                "rainfall_mm": float(row.rainfall_mm),
                "discharge_m3s": float(row.discharge_m3s),
            }
        )
    flood_days.sort(key=lambda item: (item["township_id"], item["date"]))
    cases = collapse(flood_days)
    cases.sort(
        key=lambda item: (
            -LEVEL_RANK[item["map_level"]],
            item["peak_date"],
            item["place"].lower(),
        )
    )
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(cases)

    kawa = all_days.loc[
        (all_days["township_id"] == "kawa") & (all_days["date"] == date(2026, 8, 19))
    ]
    if not kawa.empty:
        sample = kawa.iloc[0]
        print(
            "kawa 2026-08-19",
            f"{float(sample.day_probability) * 100:.1f}%",
            map_level(float(sample.day_probability)),
        )
    print(f"scored days {len(all_days)}")
    print(f"map above low: days {len(flood_days)} cases {len(cases)}")
    for level in ("severe", "high", "moderate"):
        print(level, sum(1 for item in cases if item["map_level"] == level))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
