"""High and severe cases for allocation history.

Recorded relief uses impact_severity on households + affected people / 5.
Model spells use the served gradient-boosting flood model with the same
probability bands as the map and prediction panel (high from 50%, severe
from 75%). The logistic model is not used here.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELIEF_PATH = ROOT / "data" / "processed" / "validated_daily.csv"
MODEL_PATH = ROOT / "ml" / "models" / "bago_flood_model.joblib"
META_PATH = ROOT / "ml" / "models" / "bago_flood_model_metadata.json"
OUT_PATH = ROOT / "data" / "processed" / "flood_cases_high_severe.csv"

EAST_LAT, EAST_LNG = 17.335, 96.481
WEST_LAT, WEST_LNG = 18.817, 95.217
SPLIT = 96.0
MARGIN = 0.08

COLUMNS = (
    "place",
    "township_id",
    "depot",
    "source",
    "level",
    "start_date",
    "end_date",
    "peak_date",
    "peak_score",
    "households",
    "affected_people",
    "days",
    "overlap",
)


def depot_for(latitude: float, longitude: float) -> str:
    if longitude >= SPLIT + MARGIN:
        return "Bago (east)"
    if longitude <= SPLIT - MARGIN:
        return "Pyay (west)"
    east = (latitude - EAST_LAT) ** 2 + (longitude - EAST_LNG) ** 2
    west = (latitude - WEST_LAT) ** 2 + (longitude - WEST_LNG) ** 2
    return "Bago (east)" if east <= west else "Pyay (west)"


def parse_day(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number != number:
        return None
    return number


def impact_level(score: float) -> str | None:
    if score >= 2000:
        return "severe"
    if score >= 500:
        return "high"
    return None


def blank_count(value: float | None) -> str:
    if value is None:
        return ""
    return str(int(round(value)))


def scan_relief() -> list[dict[str, str]]:
    cases: list[dict[str, str]] = []
    with RELIEF_PATH.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            households = parse_float(row.get("households"))
            people = parse_float(row.get("affected_people"))
            if households is None and people is None:
                continue
            score = max(0.0, households or 0.0) + max(0.0, people or 0.0) / 5.0
            level = impact_level(score)
            if level is None:
                continue
            latitude = parse_float(row.get("lat"))
            longitude = parse_float(row.get("lng"))
            if latitude is None or longitude is None:
                continue
            day = parse_day(row["date"]).isoformat()
            cases.append(
                {
                    "place": row["township"].strip(),
                    "township_id": row["township_id"].strip(),
                    "depot": depot_for(latitude, longitude),
                    "source": "recorded",
                    "level": level,
                    "start_date": day,
                    "end_date": day,
                    "peak_date": day,
                    "peak_score": f"{score:.2f}",
                    "households": blank_count(households),
                    "affected_people": blank_count(people),
                    "days": "1",
                    "overlap": "",
                }
            )
    return cases


def scan_model() -> list[dict[str, str]]:
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from app.services import prediction

    spec = importlib.util.spec_from_file_location(
        "map_flood_days", ROOT / "scripts" / "map_flood_days.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("map_flood_days.py not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = json.loads(META_PATH.read_text(encoding="utf-8"))
    listed = [str(name) for name in metadata.get("features") or []]
    if listed and tuple(listed) != module.FEATURES:
        raise SystemExit(f"model features changed: {listed}")
    prediction.load_model.cache_clear()
    model, _ = prediction.load_model()
    return module.model_catalog_cases(model)


def mark_overlap(recorded: list[dict[str, str]], model_cases: list[dict[str, str]]) -> None:
    spans: dict[str, list[tuple[date, date]]] = defaultdict(list)
    for case in model_cases:
        spans[case["township_id"]].append(
            (parse_day(case["start_date"]), parse_day(case["end_date"]))
        )
    for case in recorded:
        day = parse_day(case["peak_date"])
        if any(start <= day <= end for start, end in spans.get(case["township_id"], ())):
            case["overlap"] = "yes"
    recorded_days: dict[str, set[date]] = defaultdict(set)
    for case in recorded:
        if case["overlap"] == "yes":
            recorded_days[case["township_id"]].add(parse_day(case["peak_date"]))
    for case in model_cases:
        days = recorded_days.get(case["township_id"])
        if not days:
            continue
        start = parse_day(case["start_date"])
        end = parse_day(case["end_date"])
        if any(start <= day <= end for day in days):
            case["overlap"] = "yes"


def sort_key(case: dict[str, str]) -> tuple[int, str, str]:
    level_rank = 0 if case["level"] == "severe" else 1
    return (level_rank, case["peak_date"], case["place"].lower())


def main() -> None:
    recorded = scan_relief()
    model_cases = scan_model()
    mark_overlap(recorded, model_cases)
    cases = sorted(recorded + model_cases, key=sort_key)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(cases)

    def tally(rows: list[dict[str, str]], **match: str) -> int:
        return sum(1 for row in rows if all(row[key] == value for key, value in match.items()))

    print(f"wrote {len(cases)} cases to {OUT_PATH}")
    print(f"recorded {len(recorded)} model {len(model_cases)}")
    print(f"severe {tally(cases, level='severe')} high {tally(cases, level='high')}")
    print(f"overlap {tally(cases, overlap='yes')}")


if __name__ == "__main__":
    main()
