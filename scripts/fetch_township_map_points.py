"""One-off: fetch Open Admin Data township lat/lon for Bago map labels."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from urllib.parse import quote

import httpx

API_ROOT = "https://api.openadmindata.org/api/v1/mm"
BAGO_SLUG = "bago-MMR007"
OUT = Path(__file__).resolve().parents[1] / "data" / "external" / "geography" / "township_map_points.json"

BAGO_28 = (
    "Bago", "Kawa", "Thanatpin", "Waw",
    "Nyaunglebin", "Kyauktaga", "Daik-U", "Shwegyin", "Kyaukkyi",
    "Taungoo", "Oktwin", "Yedashe", "Pyu", "Htantabin",
    "Thayarwady", "Letpadan", "Minhla", "Monyo", "Okpo", "Gyobingauk",
    "Nattalin", "Zigon", "Thegon", "Paungde",
    "Pyay", "Paukkaung", "Padaung", "Shwedaung",
)


async def main() -> None:
    async with httpx.AsyncClient(timeout=30.0, headers={"User-Agent": "HydroFlow/1.0"}) as client:
        region = await client.get(f"{API_ROOT}/region/{BAGO_SLUG}.json")
        region.raise_for_status()
        payload = region.json()
        entity = payload["entity"]
        children = payload.get("children", {})
        districts = [
            item
            for item in children.get("entities", [])
            if item.get("parent_id") == entity["id"] and item.get("level") == "district"
        ]
        by_name: dict[str, dict] = {}
        for district in districts:
            slug = str(district["slug"])
            detail = await client.get(f"{API_ROOT}/district/{quote(slug)}.json")
            detail.raise_for_status()
            for township in detail.json().get("children", {}).get("entities", []):
                if township.get("level") != "township":
                    continue
                name = str(township["name_en"])
                by_name[name] = {
                    "name_en": name,
                    "latitude": float(township["lat"]),
                    "longitude": float(township["lon"]),
                    "source": "Open Admin Data",
                    "open_admin_id": str(township["id"]),
                }
        # Htantabin is documented as missing from Open Admin under Bago.
        by_name.setdefault(
            "Htantabin",
            {
                "name_en": "Htantabin",
                "latitude": 18.736925,
                "longitude": 96.520799,
                "source": "OpenStreetMap relation 5996628",
                "open_admin_id": "htantabin-taungoo",
            },
        )
        missing = [name for name in BAGO_28 if name not in by_name]
        if missing:
            raise SystemExit(f"Missing townships from Open Admin: {missing}")
        ordered = [by_name[name] for name in BAGO_28]
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"townships": ordered}, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {len(ordered)} points to {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
