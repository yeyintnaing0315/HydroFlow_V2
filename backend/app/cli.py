from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from app.db import SessionLocal
from app.services import geography, ingestion, sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HydroFlow operational data commands")
    commands = parser.add_subparsers(dest="command", required=True)
    geography_parser = commands.add_parser("import-geography")
    geography_parser.add_argument("paths", nargs="+", type=Path)
    geography_parser.add_argument("--replace", action="store_true")
    commands.add_parser("validate-geography")
    commands.add_parser("seed-sources")
    inundation = commands.add_parser("import-inundation")
    inundation.add_argument("path", type=Path)
    inundation.add_argument("--observed-at", required=True)
    inundation.add_argument("--source-url", required=True)
    images = commands.add_parser("load-inventory-images")
    images.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Photo folder. Defaults to data/inventory/objectDetect.",
    )
    args = parser.parse_args(argv)

    if args.command == "load-inventory-images":
        return _load_inventory_images(args.root)

    with SessionLocal() as session:
        if args.command == "import-geography":
            result = geography.import_ocha_geojson(session, args.paths, replace=args.replace)
        elif args.command == "validate-geography":
            result = geography.validate_bago_geography(session)
        elif args.command == "seed-sources":
            result = {
                key: {"enabled": row.enabled, "reason": row.unavailable_reason}
                for key, row in sources.ensure_sources(session).items()
            }
        else:
            count = ingestion.import_unosat_geojson(
                session,
                args.path,
                datetime.fromisoformat(args.observed_at.replace("Z", "+00:00")),
                args.source_url,
            )
            result = {"imported_inundation_features": count}
    print(json.dumps(result, indent=2, default=str))
    return 0


def _default_photo_root() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "inventory" / "objectDetect"


def _load_inventory_images(root: Path | None) -> int:
    from app.db import InventorySession
    from app.services.inventory import InventoryError
    from app.services.inventory_images import load_inventory_images

    photo_root = _default_photo_root() if root is None else root
    try:
        with InventorySession() as session:
            result = load_inventory_images(session, photo_root)
            session.commit()
    except InventoryError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
