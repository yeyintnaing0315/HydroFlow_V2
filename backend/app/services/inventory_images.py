"""Index objectDetect photos without changing Bago East or Bago West stock."""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import InventoryImage
from app.services.inventory import ITEM_TYPES, InventoryError

_REPO_ROOT = Path(__file__).resolve().parents[3]
_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
_CLASS_FOLDERS = {
    "clothes": "clothing",
    "clothing": "clothing",
    "foods": "foods",
    "kitchenware": "kitchenware",
    "utility": "utilities",
    "utilities": "utilities",
}
_ALIASES = {
    "female_cloth": ("clothing", "f_longyi"),
    "male_cloth": ("clothing", "m_longyi"),
    "m_cloth": ("clothing", "m_longyi"),
    "f_cloth": ("clothing", "f_longyi"),
    "fishcan": ("foods", "canned_fish"),
    "water dipper": ("kitchenware", "water_dipper"),
    "water_dipper": ("kitchenware", "water_dipper"),
    "water-dipper": ("kitchenware", "water_dipper"),
    "cup": ("kitchenware", "water_dipper"),
    "dipper": ("kitchenware", "water_dipper"),
    "ricebag": ("foods", "rice"),
    "bednet": ("utilities", "bednet"),
    "netbed": ("utilities", "bednet"),
    "soup": ("kitchenware", "soap"),
}


def default_catalog_csv() -> Path:
    return _REPO_ROOT / "data" / "inventory" / "image_catalog.csv"


def load_inventory_images(
    session: Session,
    root: Path,
    *,
    catalog_csv: Path | None = None,
) -> dict[str, object]:
    """Store one inventory_images row per file hash and rewrite the catalog CSV.

    The inventory database must already have inventory_images (apply schema.sql).
    Confirmed quantity stays 0. East and West balances are left untouched.
    """
    if not root.is_dir():
        raise InventoryError(f"Inventory photo folder not found: {root}")
    try:
        session.execute(text("SELECT 1 FROM inventory_images LIMIT 0"))
    except Exception as exc:
        raise InventoryError(
            "inventory_images is missing. Apply data/inventory/schema.sql before loading photos."
        ) from exc

    photos = _collect_photos(root)
    known = set(session.scalars(select(InventoryImage.content_sha256)))
    inserted = 0
    skipped = 0
    for path, category_code, item_code in photos:
        digest = _sha256(path)
        if digest in known:
            skipped += 1
            continue
        session.add(
            InventoryImage(
                relative_path=_stored_path(path),
                category_code=category_code,
                item_code=item_code,
                content_sha256=digest,
                confirmed_quantity=0,
            )
        )
        known.add(digest)
        inserted += 1
    session.flush()

    destination = catalog_csv if catalog_csv is not None else default_catalog_csv()
    rows = _write_catalog(session, destination)
    return {
        "root": root.resolve().as_posix(),
        "inserted": inserted,
        "skipped": skipped,
        "rows": rows,
        "catalog_csv": destination.resolve().as_posix(),
    }


def _collect_photos(root: Path) -> list[tuple[Path, str | None, str | None]]:
    children = {
        path.name.casefold(): path
        for path in root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    }
    for name, path in children.items():
        if name not in _CLASS_FOLDERS and name != "unassigned" and _image_files(path):
            raise InventoryError(f"Unknown photo folder: {path.name}")

    photos: list[tuple[Path, str | None, str | None]] = []
    seen_class_dirs: set[str] = set()
    for folder_name, category_code in _CLASS_FOLDERS.items():
        class_dir = children.get(folder_name)
        if class_dir is None or folder_name in seen_class_dirs:
            continue
        seen_class_dirs.add(folder_name)
        loose = [
            path
            for path in class_dir.iterdir()
            if path.is_file() and _is_image(path)
        ]
        if loose:
            raise InventoryError(
                f"Move photos into a subclass folder under {class_dir.name}."
            )
        for child in sorted(
            (path for path in class_dir.iterdir() if path.is_dir() and not path.name.startswith(".")),
            key=lambda path: path.name.casefold(),
        ):
            images = _image_files(child)
            if not images:
                continue
            category, item_code = _resolve_subclass(category_code, child.name)
            for image in images:
                photos.append((image, category, item_code))

    unassigned = children.get("unassigned")
    if unassigned is not None:
        for image in _image_files(unassigned):
            photos.append((image, None, None))
    return photos


def _resolve_subclass(parent_class: str, folder_name: str) -> tuple[str, str]:
    """Map a folder onto a real subclass and its class.

    The class is the parent folder when that subclass belongs to it, and the
    alias's own class otherwise.
    """
    raw = folder_name.casefold()
    if raw in _ALIASES:
        known_class, item_code = _ALIASES[raw]
    else:
        item_code = raw.replace("-", "_")
        known_class = _owner_class(item_code)
    if known_class is None:
        raise InventoryError(f"Unknown subclass folder: {folder_name}")
    if _owner_class(item_code) == parent_class:
        return parent_class, item_code
    return known_class, item_code


def _owner_class(item_code: str) -> str | None:
    for category_code, types in ITEM_TYPES.items():
        if any(code == item_code for code, *_rest in types):
            return category_code
    return None


def _image_files(folder: Path) -> list[Path]:
    files = [path for path in folder.rglob("*") if path.is_file() and _is_image(path)]
    return sorted(files, key=lambda path: path.as_posix().casefold())


def _is_image(path: Path) -> bool:
    return not path.name.startswith(".") and path.suffix.lower() in _IMAGE_SUFFIXES


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise InventoryError(f"Could not read photo: {path}") from exc
    return digest.hexdigest()


def _stored_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _write_catalog(session: Session, catalog_csv: Path) -> int:
    rows = list(
        session.scalars(
            select(InventoryImage).order_by(
                InventoryImage.relative_path,
                InventoryImage.content_sha256,
            )
        )
    )
    catalog_csv.parent.mkdir(parents=True, exist_ok=True)
    with catalog_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            ["path", "category_code", "item_code", "content_sha256", "confirmed_quantity"]
        )
        for row in rows:
            writer.writerow(
                [
                    row.relative_path,
                    row.category_code or "",
                    row.item_code or "",
                    row.content_sha256,
                    int(row.confirmed_quantity),
                ]
            )
    return len(rows)
