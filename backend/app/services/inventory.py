"""Depot stock for Bago East and Pyay West, stored by store_id."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import InventoryCategory, InventoryItemType, StockBalance, StockMovement, Store

DEFAULT_CATEGORIES: tuple[dict[str, object], ...] = (
    {"code": "fund", "name": "Fund", "entry_mode": "manual_only", "sort_order": 1},
    {"code": "foods", "name": "Foods", "entry_mode": "scan_or_manual", "sort_order": 2},
    {"code": "clothing", "name": "Clothing", "entry_mode": "scan_or_manual", "sort_order": 3},
    {"code": "kitchenware", "name": "Kitchenware", "entry_mode": "scan_or_manual", "sort_order": 4},
    {"code": "utilities", "name": "Utilities", "entry_mode": "scan_or_manual", "sort_order": 5},
)

DEFAULT_ITEM_TYPES: dict[str, tuple[tuple[str, str, str, int], ...]] = {
    "foods": (
        ("rice", "Rice", "bag", 1),
        ("oil", "Oil", "bottle", 2),
        ("canned_fish", "Canned fish", "can", 3),
    ),
    "clothing": (
        ("tshirt", "T-shirt", "piece", 1),
        ("m_longyi", "Men longyi", "piece", 2),
        ("f_longyi", "Women longyi", "piece", 3),
    ),
    "kitchenware": (
        ("bowl", "Bowl", "piece", 1),
        ("knife", "Knife", "piece", 2),
        ("mug", "Mug", "piece", 3),
        ("spoon", "Spoon", "piece", 4),
        ("soap", "Soap", "pack", 5),
        ("water_dipper", "Water dipper", "piece", 6),
        ("plate", "Plate", "piece", 7),
        ("pot", "Pot", "piece", 8),
    ),
    "utilities": (
        ("bednet", "Bed net", "piece", 1),
        ("blanket", "Blanket", "piece", 2),
        ("towel", "Towel", "piece", 3),
        ("box", "Box", "piece", 4),
    ),
}

# Backward-compatible aliases for ML scripts and legacy imports.
CATEGORIES = DEFAULT_CATEGORIES
ITEM_TYPES = DEFAULT_ITEM_TYPES

CATALOG_CODE_RE = re.compile(r"^[a-z0-9_]{1,40}$")

STORE_SEEDS: tuple[dict[str, object], ...] = (
    {
        "region": "east",
        "name": "Bago depot east",
        "latitude": 17.335,
        "longitude": 96.481,
    },
    {
        "region": "west",
        "name": "Pyay depot west",
        "latitude": 18.817,
        "longitude": 95.217,
    },
)

REGION_LABELS = {
    "east": "Bago East",
    "west": "Bago West",
}


ITEM_CAPACITY = Decimal("100000")
FUND_CAPACITY = Decimal("10000000000")


class InventoryError(ValueError):
    """A stock change that breaks the class rules."""


def validate_catalog_code(code: str, *, label: str = "Code") -> str:
    normalized = code.strip().lower()
    if not CATALOG_CODE_RE.fullmatch(normalized):
        raise InventoryError(f"{label} must be 1–40 lowercase letters, digits, or underscores")
    return normalized


def load_catalog(session: Session) -> tuple[list[InventoryCategory], dict[str, list[InventoryItemType]]]:
    """Return categories sorted by sort_order and item types grouped by category code."""
    categories = list(
        session.scalars(select(InventoryCategory).order_by(InventoryCategory.sort_order, InventoryCategory.code))
    )
    types_by_category: dict[str, list[InventoryItemType]] = {row.code: [] for row in categories}
    for row in session.scalars(
        select(InventoryItemType)
        .join(InventoryCategory)
        .order_by(InventoryCategory.sort_order, InventoryItemType.sort_order, InventoryItemType.code)
    ):
        types_by_category.setdefault(row.category.code, []).append(row)
    return categories, types_by_category


def item_max_quantity(category_code: str) -> Decimal:
    """Each subclass (SKU) is capped at 100,000 per depot. Fund uses its own pool."""
    return FUND_CAPACITY if category_code == "fund" else ITEM_CAPACITY


def stock_capacity(category_code: str) -> Decimal:
    """Backward-compatible alias for class-level UI totals (fund only; else per-item cap)."""
    return item_max_quantity(category_code)


def seed_catalog(session: Session) -> None:
    """Insert default classes and subclasses when missing."""
    for spec in DEFAULT_CATEGORIES:
        existing = session.scalar(
            select(InventoryCategory).where(InventoryCategory.code == spec["code"])
        )
        if existing is None:
            session.add(
                InventoryCategory(
                    code=str(spec["code"]),
                    name=str(spec["name"]),
                    entry_mode=str(spec["entry_mode"]),
                    sort_order=int(spec["sort_order"]),
                )
            )
    session.flush()
    categories = {
        row.code: row for row in session.scalars(select(InventoryCategory))
    }
    for category_code, types in DEFAULT_ITEM_TYPES.items():
        category = categories.get(category_code)
        if category is None:
            continue
        for code, name, unit, order in types:
            existing = session.scalar(
                select(InventoryItemType).where(
                    InventoryItemType.category_id == category.id,
                    InventoryItemType.code == code,
                )
            )
            if existing is None:
                session.add(
                    InventoryItemType(
                        category_id=category.id,
                        code=code,
                        name=name,
                        unit=unit,
                        sort_order=order,
                    )
                )
    session.flush()


def create_category(
    session: Session,
    *,
    code: str,
    name: str,
    entry_mode: str,
    sort_order: int | None = None,
) -> InventoryCategory:
    code = validate_catalog_code(code, label="Class code")
    name = name.strip()
    if not name:
        raise InventoryError("Class name is required")
    if entry_mode not in {"scan_or_manual", "manual_only"}:
        raise InventoryError("Entry mode must be scan_or_manual or manual_only")
    existing = session.scalar(select(InventoryCategory).where(InventoryCategory.code == code))
    if existing is not None:
        raise InventoryError(f"Class already exists: {code}")
    if sort_order is None:
        max_order = session.scalar(select(func.max(InventoryCategory.sort_order)))
        sort_order = int(max_order or 0) + 1
    row = InventoryCategory(code=code, name=name, entry_mode=entry_mode, sort_order=sort_order)
    session.add(row)
    session.flush()
    seed_regions(session)
    return row


def create_item_type(
    session: Session,
    *,
    category_code: str,
    code: str,
    name: str,
    unit: str,
    sort_order: int | None = None,
) -> InventoryItemType:
    category_code = validate_catalog_code(category_code, label="Class code")
    code = validate_catalog_code(code, label="Subclass code")
    name = name.strip()
    unit = unit.strip()
    if not name:
        raise InventoryError("Subclass name is required")
    if not unit:
        raise InventoryError("Unit is required")
    category = session.scalar(
        select(InventoryCategory).where(InventoryCategory.code == category_code)
    )
    if category is None:
        raise InventoryError(f"Unknown class: {category_code}")
    if category_code == "fund":
        raise InventoryError("Fund has no subclasses")
    existing = session.scalar(
        select(InventoryItemType).where(
            InventoryItemType.category_id == category.id,
            InventoryItemType.code == code,
        )
    )
    if existing is not None:
        raise InventoryError(f"Subclass already exists: {code}")
    if sort_order is None:
        max_order = session.scalar(
            select(func.max(InventoryItemType.sort_order)).where(
                InventoryItemType.category_id == category.id
            )
        )
        sort_order = int(max_order or 0) + 1
    row = InventoryItemType(
        category_id=category.id,
        code=code,
        name=name,
        unit=unit,
        sort_order=sort_order,
    )
    session.add(row)
    session.flush()
    seed_regions(session)
    return row


def seed_stores(session: Session) -> None:
    """Insert the Bago east and Pyay west depots when that region has no store."""
    for spec in STORE_SEEDS:
        existing = session.scalar(select(Store).where(Store.region == spec["region"]))
        if existing is None:
            session.add(
                Store(
                    region=str(spec["region"]),
                    name=str(spec["name"]),
                    latitude=float(spec["latitude"]),
                    longitude=float(spec["longitude"]),
                )
            )
    session.flush()


def store_for_region(session: Session, region: str) -> Store:
    if region not in REGION_LABELS:
        raise InventoryError("Region must be east or west")
    seed_stores(session)
    store = session.scalar(select(Store).where(Store.region == region).order_by(Store.id))
    if store is None:
        raise InventoryError("Region must be east or west")
    return store


def seed_regions(session: Session) -> None:
    """Ensure both depots exist and every catalog SKU has a balance row."""
    seed_catalog(session)
    seed_stores(session)
    categories, types_by_category = load_catalog(session)
    stores = list(session.scalars(select(Store).where(Store.region.in_(("east", "west")))))
    for store in stores:
        for category in categories:
            if category.code == "fund":
                fund = session.scalar(
                    select(StockBalance).where(
                        StockBalance.store_id == store.id,
                        StockBalance.category_code == "fund",
                        StockBalance.item_code.is_(None),
                    )
                )
                if fund is None:
                    session.add(
                        StockBalance(
                            store_id=store.id,
                            category_code="fund",
                            item_code=None,
                            quantity=Decimal("0"),
                            unit="mmk",
                        )
                    )
                continue
            for item_type in types_by_category.get(category.code, []):
                existing = session.scalar(
                    select(StockBalance).where(
                        StockBalance.store_id == store.id,
                        StockBalance.category_code == category.code,
                        StockBalance.item_code == item_type.code,
                    )
                )
                if existing is None:
                    session.add(
                        StockBalance(
                            store_id=store.id,
                            category_code=category.code,
                            item_code=item_type.code,
                            quantity=Decimal("0"),
                            unit=item_type.unit,
                        )
                    )
        # Manual-only classes with no subclasses yet: one aggregate row is not used; fund handled above.
        for category in categories:
            if category.entry_mode == "manual_only" and category.code != "fund":
                existing = session.scalar(
                    select(StockBalance).where(
                        StockBalance.store_id == store.id,
                        StockBalance.category_code == category.code,
                        StockBalance.item_code.is_(None),
                    )
                )
                if existing is None and not types_by_category.get(category.code):
                    session.add(
                        StockBalance(
                            store_id=store.id,
                            category_code=category.code,
                            item_code=None,
                            quantity=Decimal("0"),
                            unit="piece",
                        )
                    )
    session.flush()


def _class_name(session: Session, category_code: str) -> str:
    row = session.scalar(
        select(InventoryCategory).where(InventoryCategory.code == category_code)
    )
    return row.name if row is not None else category_code


def _item_name(session: Session, category_code: str, item_code: str | None) -> str:
    if item_code is None:
        return _class_name(session, category_code)
    row = session.scalar(
        select(InventoryItemType)
        .join(InventoryCategory)
        .where(
            InventoryCategory.code == category_code,
            InventoryItemType.code == item_code,
        )
    )
    return row.name if row is not None else (item_code or category_code)


def region_snapshot(session: Session, region: str) -> dict[str, object]:
    if region not in REGION_LABELS:
        raise InventoryError("Region must be east or west")
    seed_regions(session)
    store = store_for_region(session, region)
    categories, types_by_category = load_catalog(session)
    balances = list(
        session.scalars(select(StockBalance).where(StockBalance.store_id == store.id))
    )
    classes = []
    for category in categories:
        code = category.code
        catalog_codes = {t.code for t in types_by_category.get(code, [])}
        rows = [
            row
            for row in balances
            if row.category_code == code and (code == "fund" or row.item_code in catalog_codes or row.item_code is None)
        ]
        if code != "fund":
            rows = [row for row in rows if row.item_code is not None]
        items = [
            {
                "code": row.item_code,
                "name": _item_name(session, code, row.item_code),
                "quantity": float(row.quantity),
                "unit": row.unit,
                "capacity": float(item_max_quantity(code)),
            }
            for row in sorted(rows, key=lambda row: row.item_code or "")
        ]
        if code == "fund":
            class_capacity = float(FUND_CAPACITY)
        else:
            class_capacity = float(len(items) * ITEM_CAPACITY)
        classes.append(
            {
                "code": code,
                "name": category.name,
                "entry_mode": category.entry_mode,
                "quantity": sum(item["quantity"] for item in items),
                "capacity": class_capacity,
                "items": items,
            }
        )
    movements = list(
        session.scalars(
            select(StockMovement)
            .where(StockMovement.store_id == store.id)
            .order_by(StockMovement.created_at.desc())
            .limit(20)
        )
    )
    return {
        "region": region,
        "location": REGION_LABELS[region],
        "classes": classes,
        "movements": [
            {
                "id": row.id,
                "category_code": row.category_code,
                "item_code": row.item_code,
                "name": _item_name(session, row.category_code, row.item_code),
                "class_name": _class_name(session, row.category_code),
                "direction": row.direction,
                "entry_mode": row.entry_mode,
                "quantity": float(row.quantity),
                "unit": next(
                    (
                        item["unit"]
                        for class_row in classes
                        if class_row["code"] == row.category_code
                        for item in class_row["items"]
                        if item["code"] == row.item_code
                    ),
                    "mmk" if row.category_code == "fund" else "piece",
                ),
                "created_at": row.created_at.isoformat(),
            }
            for row in movements
        ],
    }


def add_region_stock(
    session: Session,
    *,
    region: str,
    category_code: str,
    quantity: Decimal | int | str,
    entry_mode: str,
    direction: str = "in",
    item_code: str | None = None,
    note: str | None = None,
    allocation_line_id: int | None = None,
    detection_session_id: int | None = None,
) -> dict[str, object]:
    if region not in REGION_LABELS:
        raise InventoryError("Region must be east or west")
    amount = Decimal(quantity)
    if amount <= 0:
        raise InventoryError("Quantity must be greater than zero")
    if entry_mode not in {"manual", "scan"}:
        raise InventoryError("Entry mode must be manual or scan")
    if direction not in {"in", "out"}:
        raise InventoryError("Direction must be in or out")
    seed_regions(session)
    store = store_for_region(session, region)
    category = session.scalar(
        select(InventoryCategory).where(InventoryCategory.code == category_code)
    )
    if category is None:
        raise InventoryError(f"Unknown class: {category_code}")
    if category.entry_mode == "manual_only" and entry_mode != "manual":
        raise InventoryError("Fund can only be added manually")
    if category_code == "fund":
        if item_code:
            raise InventoryError("Fund has no subclass")
        item_code = None
    else:
        if not item_code:
            raise InventoryError("Choose a subclass of this class")
        item_row = session.scalar(
            select(InventoryItemType)
            .join(InventoryCategory)
            .where(
                InventoryCategory.code == category_code,
                InventoryItemType.code == item_code,
            )
        )
        if item_row is None:
            raise InventoryError("Choose a subclass of this class")

    statement = select(StockBalance).where(
        StockBalance.store_id == store.id,
        StockBalance.category_code == category_code,
    )
    if item_code is None:
        statement = statement.where(StockBalance.item_code.is_(None))
    else:
        statement = statement.where(StockBalance.item_code == item_code)
    balance = session.scalar(statement)
    if balance is None:
        raise InventoryError("Stock row is missing for this class")
    _guard_capacity(session, balance, category_code, amount, direction)
    current = Decimal(balance.quantity)
    updated = current + amount if direction == "in" else current - amount
    if updated < 0:
        raise InventoryError("Allocation is larger than the stock on hand")
    balance.quantity = updated
    session.add(
        StockMovement(
            store_id=store.id,
            category_code=category_code,
            item_code=item_code,
            direction=direction,
            entry_mode=entry_mode,
            quantity=amount,
            allocation_line_id=allocation_line_id,
            detection_session_id=detection_session_id,
            note=note,
            created_at=datetime.now(timezone.utc),
        )
    )
    session.flush()
    return region_snapshot(session, region)


def _guard_capacity(
    session: Session,
    balance: StockBalance,
    category_code: str,
    amount: Decimal,
    direction: str,
) -> None:
    """Block a receipt that would push this subclass row over its maximum."""
    if direction != "in":
        return
    cap = item_max_quantity(category_code)
    current = Decimal(balance.quantity)
    if current + amount > cap:
        label = _item_name(session, category_code, balance.item_code)
        raise InventoryError(f"{label} is limited to {int(cap)}")


DEMO_STOCK: dict[str, tuple[tuple[str, str, int], ...]] = {
    "east": (
        ("foods", "rice", 100),
        ("foods", "oil", 500),
        ("foods", "canned_fish", 200),
        ("clothing", "tshirt", 3500),
        ("utilities", "blanket", 800),
        ("kitchenware", "water_dipper", 1200),
    ),
    "west": (
        ("foods", "rice", 80),
        ("foods", "oil", 120),
        ("clothing", "tshirt", 600),
        ("utilities", "blanket", 150),
    ),
}


def ensure_demo_stock(session: Session) -> None:
    """Load demo quantities when both depots are empty (local development)."""
    seed_regions(session)
    for region, lines in DEMO_STOCK.items():
        snapshot = region_snapshot(session, region)
        total = sum(
            float(item["quantity"])
            for klass in snapshot.get("classes", [])
            for item in klass.get("items", [])
        )
        if total > 0:
            continue
        for category_code, item_code, quantity in lines:
            add_region_stock(
                session,
                region=region,
                category_code=category_code,
                item_code=item_code,
                quantity=quantity,
                entry_mode="manual",
                direction="in",
                note="Demo seed stock",
            )
