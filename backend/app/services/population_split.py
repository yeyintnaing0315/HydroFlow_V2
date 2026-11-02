"""Split affected totals by census sex ratio."""

from __future__ import annotations

from app.services import census


def split_affected_by_sex(
    township_name_en: str,
    affected_total: int,
) -> tuple[int, int, int]:
    total = max(0, int(affected_total))
    if total <= 0:
        return 0, 0, 0
    try:
        profile = census.township_profile(township_name_en)
    except census.CensusUnavailableError:
        return total, 0, 0
    if profile is None:
        return total, 0, 0
    _district, township = profile
    male_base = int(township.population.male)
    female_base = int(township.population.female)
    base = male_base + female_base
    if base <= 0:
        return total, 0, 0
    male = int(round(total * male_base / base))
    female = max(0, total - male)
    return total, male, female
