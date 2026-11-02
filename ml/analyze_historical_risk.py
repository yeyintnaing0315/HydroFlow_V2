"""Score all historical rows and summarize high/severe model vs recorded floods."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.flood_history import impact_severity  # noqa: E402
from app.services.prediction import feature_names, load_model  # noqa: E402
from app.services.prediction_secondary import load_secondary_model  # noqa: E402
from app.services.prediction_timeline import probability_risk_level  # noqa: E402

DAILY = ROOT / "data" / "raw" / "bago_daily.csv"
HUMIDITY = ROOT / "data" / "external" / "nasa_power_daily.csv"
ARCHIVE_DIR = ROOT / "data" / "external" / "open_meteo_archive_daily"
NASA_T2M_DIR = ROOT / "data" / "external" / "nasa_power_t2m_ws2m"


def _window_sum(values: list[float], index: int, size: int) -> float | None:
    start = index - size + 1
    if start < 0:
        return None
    chunk = values[start : index + 1]
    if len(chunk) != size:
        return None
    return float(sum(chunk))


def _lag(values: list[float], index: int, offset: int) -> float | None:
    source = index - offset
    if source < 0:
        return None
    return float(values[source])


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for township_id, group in frame.groupby("township_id", sort=False):
        ordered = group.sort_values("date").reset_index(drop=True)
        rains = ordered["rainfall_mm"].astype(float).tolist()
        discharges = ordered["river_discharge_m3s"].astype(float).tolist()
        for index, record in ordered.iterrows():
            day = pd.Timestamp(record["date"]).date()
            day_number = day.timetuple().tm_yday
            lag1 = _lag(discharges, index, 1)
            lag2 = _lag(discharges, index, 2)
            lag3 = _lag(discharges, index, 3)
            lag_mean = None if None in (lag1, lag2, lag3) else (lag1 + lag2 + lag3) / 3
            rows.append(
                {
                    "date": pd.Timestamp(day),
                    "township_id": township_id,
                    "township": record["township"],
                    "flood": int(record["flood"]),
                    "households": record.get("households"),
                    "affected_people": record.get("affected_people"),
                    "rainfall_1d_mm": rains[index],
                    "rainfall_3d_mm": _window_sum(rains, index, 3),
                    "rainfall_7d_mm": _window_sum(rains, index, 7),
                    "rainfall_14d_mm": _window_sum(rains, index, 14),
                    "rainfall_30d_mm": _window_sum(rains, index, 30),
                    "temperature_c": record.get("temperature_c"),
                    "relative_humidity_pct": record.get("relative_humidity_pct"),
                    "wind_speed_m_s": record.get("wind_speed_m_s"),
                    "latitude": float(record["lat"]),
                    "longitude": float(record["lng"]),
                    "day_of_year_sin": math.sin(2 * math.pi * day_number / 365.25),
                    "day_of_year_cos": math.cos(2 * math.pi * day_number / 365.25),
                    "discharge_lag_1d_m3s": lag1,
                    "discharge_lag_3d_mean_m3s": lag_mean,
                }
            )
    return pd.DataFrame(rows)


def enrich_meteorology(frame: pd.DataFrame) -> pd.DataFrame:
    humidity = pd.read_csv(HUMIDITY, parse_dates=["date"])[
        ["township_id", "date", "relative_humidity_pct"]
    ].rename(columns={"relative_humidity_pct": "rh_nasa"})
    merged = frame.merge(humidity, on=["township_id", "date"], how="left")
    merged["relative_humidity_pct"] = merged["relative_humidity_pct"].fillna(merged["rh_nasa"])
    merged = merged.drop(columns=["rh_nasa"])

    archive_frames: list[pd.DataFrame] = []
    for path in ARCHIVE_DIR.glob("*.csv"):
        township_id = path.stem
        archive = pd.read_csv(path, parse_dates=["date"])
        archive["township_id"] = township_id
        archive_frames.append(
            archive.rename(
                columns={
                    "temperature_c": "temperature_om",
                    "wind_speed_m_s": "wind_om",
                    "relative_humidity_pct": "rh_om",
                }
            )
        )
    if archive_frames:
        archives = pd.concat(archive_frames, ignore_index=True)
        merged = merged.merge(archives, on=["township_id", "date"], how="left")
        merged["temperature_c"] = merged["temperature_c"].fillna(merged["temperature_om"])
        merged["wind_speed_m_s"] = merged["wind_speed_m_s"].fillna(merged["wind_om"])
        merged["relative_humidity_pct"] = merged["relative_humidity_pct"].fillna(merged["rh_om"])
        merged = merged.drop(columns=["temperature_om", "wind_om", "rh_om"], errors="ignore")

    t2m_rows: list[dict] = []
    if NASA_T2M_DIR.is_dir():
        for nasa_json in NASA_T2M_DIR.glob("*.json"):
            township_id = nasa_json.stem
            payload = json.loads(nasa_json.read_text(encoding="utf-8"))
            temperature = payload["properties"]["parameter"]["T2M"]
            wind = payload["properties"]["parameter"]["WS2M"]
            for key in set(temperature) & set(wind):
                temp = temperature[key]
                w = wind[key]
                if temp <= -999 or w <= -999:
                    continue
                t2m_rows.append(
                    {
                        "township_id": township_id,
                        "date": pd.to_datetime(key, format="%Y%m%d"),
                        "temperature_nasa": temp,
                        "wind_nasa": w,
                    }
                )
    if t2m_rows:
        nasa = pd.DataFrame(t2m_rows)
        merged = merged.merge(nasa, on=["township_id", "date"], how="left")
        merged["temperature_c"] = merged["temperature_c"].fillna(merged["temperature_nasa"])
        merged["wind_speed_m_s"] = merged["wind_speed_m_s"].fillna(merged["wind_nasa"])
        merged = merged.drop(columns=["temperature_nasa", "wind_nasa"])
    return merged


def main() -> None:
    load_model.cache_clear()
    names = feature_names()
    primary_model, _meta = load_model()
    try:
        secondary_pipeline, _sec_meta = load_secondary_model()
    except Exception:
        secondary_pipeline = None

    daily = pd.read_csv(DAILY, parse_dates=["date"])
    features = enrich_meteorology(build_features(daily))
    complete = features.dropna(subset=names)
    dropped = len(features) - len(complete)
    print(f"Rows total: {len(features)} | scoreable (complete features): {len(complete)} | dropped: {dropped}")

    batch = complete[names]
    hgb_probs = primary_model.predict_proba(batch)[:, 1]
    hgb_threshold = float(_meta.get("decision_threshold", 0.05))
    sec_probs = None
    if secondary_pipeline is not None:
        sec_probs = secondary_pipeline.predict_proba(batch)[:, 1]

    records: list[dict] = []
    for index, row in enumerate(complete.itertuples(index=False)):
        prob = float(hgb_probs[index])
        predicted = int(prob >= hgb_threshold)
        sec_prob = None if sec_probs is None else float(sec_probs[index])
        h = 0.0 if pd.isna(row.households) else float(row.households)
        a = 0.0 if pd.isna(row.affected_people) else float(row.affected_people)
        impact = impact_severity(h, a)
        level = probability_risk_level(float(prob))
        sec_level = probability_risk_level(sec_prob) if sec_prob is not None else None
        records.append(
            {
                "date": row.date,
                "township_id": row.township_id,
                "township": row.township,
                "flood": int(row.flood),
                "impact_severity": impact,
                "hgb_probability": float(prob),
                "hgb_risk": level,
                "hgb_predicted_flood": int(predicted),
                "logistic_probability": sec_prob,
                "logistic_risk": sec_level,
            }
        )

    scored = pd.DataFrame(records)
    for model in ("hgb", "logistic"):
        risk_col = f"{model}_risk"
        subset = scored[scored[risk_col].isin(["high", "severe"])]
        print(f"\n=== {model.upper()} high/severe predictions (probability bands) ===")
        print(f"Count: {len(subset)} / {len(scored)} ({100 * len(subset) / len(scored):.2f}%)")
        flood_hits = subset[subset["flood"] == 1]
        print(f"  Overlap with recorded flood=1: {len(flood_hits)} ({100 * len(flood_hits) / max(1, len(subset)):.1f}% of high/severe)")
        impact_hi = subset[subset["impact_severity"].isin(["high", "severe"])]
        print(f"  Overlap with validated impact high/severe: {len(impact_hi)}")

    floods = scored[scored["flood"] == 1]
    print("\n=== Recorded flood days (ground truth flood=1) ===")
    print(f"Count: {len(floods)}")
    for model in ("hgb", "logistic"):
        risk_col = f"{model}_risk"
        caught = floods[floods[risk_col].isin(["high", "severe"])]
        print(f"  {model.upper()} flagged high/severe on flood day: {len(caught)} ({100 * len(caught) / len(floods):.1f}%)")

    impact_hi = scored[scored["impact_severity"].isin(["high", "severe"])]
    print("\n=== Validated impact high/severe (relief severity rule) ===")
    print(f"Count: {len(impact_hi)}")
    for model in ("hgb", "logistic"):
        risk_col = f"{model}_risk"
        caught = impact_hi[impact_hi[risk_col].isin(["high", "severe"])]
        print(f"  {model.upper()} also high/severe: {len(caught)} ({100 * len(caught) / len(impact_hi):.1f}%)")

    print("\n=== Top 15 validated severe impacts vs model scores ===")
    severe = scored[scored["impact_severity"] == "severe"].sort_values(["date"], ascending=False).head(15)
    cols = [
        "date",
        "township",
        "affected_people" if "affected_people" in severe.columns else "township_id",
        "hgb_probability",
        "hgb_risk",
        "logistic_probability",
        "logistic_risk",
        "flood",
    ]
    # merge affected back
    severe = severe.merge(
        daily[["date", "township_id", "affected_people", "households"]],
        on=["date", "township_id"],
        how="left",
    )
    print(
        severe[
            [
                "date",
                "township",
                "households",
                "affected_people",
                "hgb_probability",
                "hgb_risk",
                "logistic_probability",
                "logistic_risk",
            ]
        ].to_string(index=False)
    )

    print("\n=== Dates with most townships at HGB high/severe ===")
    hot = (
        scored[scored["hgb_risk"].isin(["high", "severe"])]
        .groupby("date")
        .size()
        .sort_values(ascending=False)
        .head(10)
    )
    for day, count in hot.items():
        floods_on_day = int(scored.loc[(scored["date"] == day) & (scored["flood"] == 1)].shape[0])
        print(f"  {day}: {count} townships high/severe | {floods_on_day} recorded floods that day")


if __name__ == "__main__":
    main()
