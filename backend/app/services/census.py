import json
import os
from functools import lru_cache
from pathlib import Path

from app.schemas.api import CensusResponse, DistrictCensus, TownshipCensus


class CensusUnavailableError(FileNotFoundError):
    """The Bago census reference file is missing or unreadable."""


def census_path() -> Path:
    default = Path(__file__).resolve().parents[3] / "data" / "external" / "bago_census_2024.json"
    return Path(os.getenv("CENSUS_PATH", default))


@lru_cache(maxsize=1)
def load_census() -> CensusResponse:
    path = census_path()
    if not path.is_file():
        raise CensusUnavailableError("Bago census reference is unavailable")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return CensusResponse.model_validate(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise CensusUnavailableError("Bago census reference could not be read") from exc


def township_profile(name_en: str) -> tuple[DistrictCensus, TownshipCensus] | None:
    census = load_census()
    for district in census.districts:
        for township in district.townships:
            if township.name_en == name_en:
                return district, township
    return None
