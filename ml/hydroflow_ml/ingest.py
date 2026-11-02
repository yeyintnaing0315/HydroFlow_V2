from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .config import CANONICAL_DATA, RAW_DATA
from .validation import ValidationReport, validate_daily_data


def load_raw(path: Path = RAW_DATA) -> pd.DataFrame:
    """Load source data without mutating or deriving model features."""
    data = pd.read_csv(path)
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    return data


def ingest(
    source: Path = RAW_DATA,
    destination: Path = CANONICAL_DATA,
) -> tuple[pd.DataFrame, ValidationReport]:
    data = load_raw(source)
    report = validate_daily_data(data)
    data = data.sort_values(["date", "township_id"], kind="stable").reset_index(drop=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(destination, index=False, date_format="%Y-%m-%d")
    report_path = destination.with_suffix(".validation.json")
    report_path.write_text(json.dumps(report.as_dict(), indent=2), encoding="utf-8")
    return data, report
