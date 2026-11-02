"""Build the Bago 2024 census reference from the region workbook.

The workbook is the source. This module writes the structured JSON the API
loads. Age groups are published for the region and districts. Township rows
carry population, household size, and dwelling type.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

REGION_LOCAL = "ပဲခူးတိုင်းဒေသကြီး"
URBAN_LOCAL = "မြို့ပြ"
RURAL_LOCAL = "ကျေးလက်"
OPEN_AGE_LOCAL = "90 နှစ်နှင့်အထက်"

DISTRICT_ORDER = ("Bago", "Nyaunglebin", "Taungoo", "Thayarwady", "Nattalin", "Pyay")
TOWNSHIP_ORDER = {
    "Bago": ("Bago", "Kawa", "Thanatpin", "Waw"),
    "Nyaunglebin": ("Nyaunglebin", "Kyauktaga", "Daik-U", "Shwegyin", "Kyaukkyi"),
    "Taungoo": ("Taungoo", "Oktwin", "Yedashe", "Pyu", "Htantabin"),
    "Thayarwady": ("Thayarwady", "Letpadan", "Minhla", "Monyo", "Okpo", "Gyobingauk"),
    "Nattalin": ("Nattalin", "Zigon", "Thegon", "Paungde"),
    "Pyay": ("Pyay", "Paukkaung", "Padaung", "Shwedaung"),
}
DISTRICTS = {
    "ညောင်လေးပင်ခရိုင်": "Nyaunglebin",
    "တောင်ငူခရိုင်": "Taungoo",
    "နတ်တလင်းခရိုင်": "Nattalin",
    "ပဲခူးခရိုင်": "Bago",
    "ပြည်ခရိုင်": "Pyay",
    "သာယာဝတီခရိုင်": "Thayarwady",
}
TOWNSHIPS = {
    "ကျောက်ကြီးမြို့နယ်": "Kyaukkyi",
    "ကျောက်တံခါးမြို့နယ်": "Kyauktaga",
    "ညောင်လေးပင်မြို့နယ်": "Nyaunglebin",
    "ဒိုက်ဦးမြို့နယ်": "Daik-U",
    "ရွှေကျင်မြို့နယ်": "Shwegyin",
    "တောင်ငူမြို့နယ်": "Taungoo",
    "ထန်းတပင်မြို့နယ်": "Htantabin",
    "ဖြူးမြို့နယ်": "Pyu",
    "ရေတာရှည်မြို့နယ်": "Yedashe",
    "အုတ်တွင်းမြို့နယ်": "Oktwin",
    "ဇီးကုန်းမြို့နယ်": "Zigon",
    "နတ်တလင်းမြို့နယ်": "Nattalin",
    "ပေါင်းတည်မြို့နယ်": "Paungde",
    "သဲကုန်းမြို့နယ်": "Thegon",
    "ကဝမြို့နယ်": "Kawa",
    "ပဲခူးမြို့နယ်": "Bago",
    "ဝေါမြို့နယ်": "Waw",
    "သနပ်ပင်မြို့နယ်": "Thanatpin",
    "ပေါက်ခေါင်းမြို့နယ်": "Paukkaung",
    "ပန်းတောင်းမြို့နယ်": "Padaung",
    "ပြည်မြို့နယ်": "Pyay",
    "ရွှေတောင်မြို့နယ်": "Shwedaung",
    "ကြို့ပင်ကောက်မြို့နယ်": "Gyobingauk",
    "မိုးညိုမြို့နယ်": "Monyo",
    "မင်းလှမြို့နယ်": "Minhla",
    "လက်ပံတန်းမြို့နယ်": "Letpadan",
    "သာယာဝတီမြို့နယ်": "Thayarwady",
    "အုတ်ဖိုမြို့နယ်": "Okpo",
}
DWELLING_FIELDS = (
    ("apartment", "တိုက်ခန်းတွဲ/ တိုက်ခန်း", "Apartment or flat"),
    ("brick", "တိုက်အိမ်", "Brick house"),
    ("semi_brick", "တိုက်ခံအိမ်", "Semi-brick house"),
    ("wooden", "ပျဉ်ထောင်အိမ်/ သစ်သားအိမ်", "Wooden house"),
    ("bamboo", "ဝါးအိမ်", "Bamboo house"),
    ("hut", "တဲအိမ်", "Hut"),
    ("other", "အခြား", "Other"),
)
SIZE_LABELS = ("1", "2", "3", "4", "5", "6", "7", "8", "9+")


def census_json_path(root: Path | None = None) -> Path:
    base = root or Path(__file__).resolve().parents[2]
    return base / "data" / "external" / "bago_census_2024.json"


def workbook_path(root: Path | None = None) -> Path:
    base = root or Path(__file__).resolve().parents[2]
    return base / "data" / "2024_census_bago_report (update).xlsx"


def _count(value: object) -> int:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("Census cell is empty")
    number = int(round(float(value)))
    if number < 0:
        raise ValueError("Census count is negative")
    return number


def _label(value: object) -> str:
    return str(value).strip()


def _sex(row: pd.Series, start: int) -> dict[str, int]:
    return {
        "total": _count(row.iloc[start]),
        "male": _count(row.iloc[start + 1]),
        "female": _count(row.iloc[start + 2]),
    }


def _place(name_local: str) -> tuple[str, str, str]:
    if name_local in DISTRICTS:
        return "district", DISTRICTS[name_local], name_local
    if name_local in TOWNSHIPS:
        return "township", TOWNSHIPS[name_local], name_local
    raise ValueError(f"Unmapped census place: {name_local}")


def _age(label: str) -> dict[str, int | str | None] | None:
    if label == OPEN_AGE_LOCAL:
        return {"label": "90+", "min_age": 90, "max_age": None}
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", label)
    if match is None:
        return None
    return {
        "label": f"{match.group(1)}-{match.group(2)}",
        "min_age": int(match.group(1)),
        "max_age": int(match.group(2)),
    }


def _sizes(row: pd.Series) -> dict[str, object]:
    buckets = [
        {"size": label, "households": _count(row.iloc[index + 2])}
        for index, label in enumerate(SIZE_LABELS)
    ]
    total = _count(row.iloc[1])
    if sum(item["households"] for item in buckets) != total:
        raise ValueError(f"Household sizes do not add up for {_label(row.iloc[0])}")
    return {"total": total, "by_size": buckets}


def _dwelling(row: pd.Series) -> dict[str, int]:
    counts = {
        key: _count(row.iloc[index + 2]) for index, (key, _local, _english) in enumerate(DWELLING_FIELDS)
    }
    total = _count(row.iloc[1])
    if sum(counts.values()) != total:
        raise ValueError(f"Dwelling types do not add up for {_label(row.iloc[0])}")
    return {"total": total, **counts}


def _sex_ok(counts: dict[str, int], label: str) -> None:
    if counts["male"] + counts["female"] != counts["total"]:
        raise ValueError(f"Male and female counts do not add up for {label}")


def _read_population(frame: pd.DataFrame) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, object]]]:
    region: dict[str, dict[str, int]] = {}
    places: dict[str, dict[str, object]] = {}
    current_district: str | None = None
    for _, row in frame.iloc[4:].iterrows():
        name = _label(row.iloc[0])
        counts = _sex(row, 1)
        _sex_ok(counts, name)
        if name == REGION_LOCAL:
            region["total"] = counts
            continue
        if name == URBAN_LOCAL:
            region["urban"] = counts
            continue
        if name == RURAL_LOCAL:
            region["rural"] = counts
            continue
        level, english, local = _place(name)
        if level == "district":
            current_district = english
            places[english] = {
                "name_en": english,
                "name_local": local,
                "population": counts,
                "townships": {},
            }
            continue
        if current_district is None:
            raise ValueError(f"Township {english} has no district")
        places[current_district]["townships"][english] = {
            "name_en": english,
            "name_local": local,
            "population": counts,
        }
    if set(region) != {"total", "urban", "rural"}:
        raise ValueError("Region population is missing urban or rural residence")
    urban_rural = {
        key: region["urban"][key] + region["rural"][key] for key in ("total", "male", "female")
    }
    if urban_rural != region["total"]:
        raise ValueError("Urban and rural population do not add up to the region")
    return region, places


def _read_ages(frame: pd.DataFrame) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    current = "region"
    for _, row in frame.iloc[3:].iterrows():
        name = _label(row.iloc[0])
        age = _age(name)
        if age is None:
            if name == REGION_LOCAL:
                current = "region"
                continue
            level, english, _local = _place(name)
            if level != "district":
                raise ValueError(f"Age table contains a township row: {name}")
            current = english
            continue
        total = _sex(row, 1)
        urban = _sex(row, 4)
        rural = _sex(row, 7)
        for counts, label in ((total, name), (urban, name), (rural, name)):
            _sex_ok(counts, label)
        combined = {key: urban[key] + rural[key] for key in ("total", "male", "female")}
        if combined != total:
            raise ValueError(f"Urban and rural age counts do not add up for {current} {name}")
        grouped.setdefault(current, []).append({**age, "total": total, "urban": urban, "rural": rural})
    return grouped


def _read_sizes(frame: pd.DataFrame) -> dict[str, dict[str, object]]:
    sizes: dict[str, dict[str, object]] = {}
    for _, row in frame.iloc[3:].iterrows():
        name = _label(row.iloc[0])
        if name == REGION_LOCAL:
            sizes["region"] = _sizes(row)
            continue
        _level, english, _local = _place(name)
        sizes[english] = _sizes(row)
    return sizes


def _read_dwellings(frame: pd.DataFrame) -> dict[str, dict[str, int]]:
    dwellings: dict[str, dict[str, int]] = {}
    for _, row in frame.iloc[3:].iterrows():
        name = _label(row.iloc[0])
        counts = _dwelling(row)
        if name == REGION_LOCAL:
            dwellings["region"] = counts
        elif name == URBAN_LOCAL:
            dwellings["urban"] = counts
        elif name == RURAL_LOCAL:
            dwellings["rural"] = counts
        else:
            _level, english, _local = _place(name)
            dwellings[english] = counts
    return dwellings


def _attach_households(
    sizes: dict[str, dict[str, object]], dwellings: dict[str, dict[str, int]], key: str
) -> dict[str, object]:
    size_row = sizes[key]
    dwelling_row = dwellings[key]
    if size_row["total"] != dwelling_row["total"]:
        raise ValueError(f"Household totals disagree for {key}")
    return {"total": size_row["total"], "by_size": size_row["by_size"], "by_dwelling": dwelling_row}


def build_census(path: Path) -> dict[str, object]:
    population, places = _read_population(pd.read_excel(path, sheet_name="Table A-1", header=None))
    ages = _read_ages(pd.read_excel(path, sheet_name="Table A-4", header=None))
    sizes = _read_sizes(pd.read_excel(path, sheet_name="Table A-11", header=None))
    dwellings = _read_dwellings(pd.read_excel(path, sheet_name="Table B-1", header=None))

    if set(places) != set(DISTRICT_ORDER):
        raise ValueError("Census districts do not match the six Bago districts")
    for district_name, township_names in TOWNSHIP_ORDER.items():
        found = set(places[district_name]["townships"])
        if found != set(township_names):
            raise ValueError(f"{district_name} townships do not match the admin list")
        district_people = places[district_name]["population"]["total"]
        township_people = sum(
            places[district_name]["townships"][name]["population"]["total"] for name in township_names
        )
        if township_people != district_people:
            raise ValueError(f"{district_name} township population does not match the district")
        age_people = sum(item["total"]["total"] for item in ages[district_name])
        if age_people != district_people:
            raise ValueError(f"{district_name} age groups do not match the district population")

    region_people = population["total"]["total"]
    if sum(places[name]["population"]["total"] for name in DISTRICT_ORDER) != region_people:
        raise ValueError("District population does not match the region")
    if sum(item["total"]["total"] for item in ages["region"]) != region_people:
        raise ValueError("Region age groups do not match the region population")

    districts = []
    for district_name in DISTRICT_ORDER:
        district = places[district_name]
        townships = []
        for township_name in TOWNSHIP_ORDER[district_name]:
            township = district["townships"][township_name]
            townships.append({**township, "households": _attach_households(sizes, dwellings, township_name)})
        districts.append(
            {
                "name_en": district["name_en"],
                "name_local": district["name_local"],
                "population": district["population"],
                "age_groups": ages[district_name],
                "households": _attach_households(sizes, dwellings, district_name),
                "townships": townships,
            }
        )

    return {
        "source": "2024 Population and Housing Census, Bago Region tables",
        "source_file": "data/2024_census_bago_report (update).xlsx",
        "census_year": 2024,
        "region_name_en": "Bago",
        "region_name_local": REGION_LOCAL,
        "notes": [
            "Counts are the published census tables, including the workbook's estimated population.",
            "Urban and rural residence is published for the region, and for age groups at region and district level.",
            "Age groups are not published for individual townships.",
            "Household size and dwelling type describe the living situation at region, district, and township level.",
            "Urban and rural dwelling type is published for the region only.",
        ],
        "dwelling_types": [
            {"key": key, "name_local": local, "name_en": english}
            for key, local, english in DWELLING_FIELDS
        ],
        "population": population,
        "age_groups": ages["region"],
        "households": {
            **_attach_households(sizes, dwellings, "region"),
            "urban_dwellings": dwellings["urban"],
            "rural_dwellings": dwellings["rural"],
        },
        "districts": districts,
    }


def write_census(source: Path | None = None, destination: Path | None = None) -> Path:
    payload = build_census(source or workbook_path())
    target = destination or census_json_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target
