from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_inventory_db
from app.main import app
from app.models import InventoryImage, StockBalance, Store
from app.services.inventory import (
    InventoryError,
    STORE_SEEDS,
    add_region_stock,
    ensure_demo_stock,
    region_snapshot,
    create_category,
    create_item_type,
    seed_catalog,
    seed_regions,
)
from app.services.inventory_images import load_inventory_images


@pytest.fixture()
def inventory_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        seed_catalog(session)
        seed_regions(session)
        session.commit()
        yield session
    Base.metadata.drop_all(engine)


def _quantity(snapshot: dict, category_code: str, item_code: str | None) -> float:
    klass = next(row for row in snapshot["classes"] if row["code"] == category_code)
    return next(item["quantity"] for item in klass["items"] if item["code"] == item_code)


def test_east_stock_does_not_change_west(inventory_session: Session) -> None:
    add_region_stock(
        inventory_session,
        region="east",
        category_code="foods",
        item_code="rice",
        quantity=4,
        entry_mode="manual",
    )
    east = region_snapshot(inventory_session, "east")
    west = region_snapshot(inventory_session, "west")
    assert _quantity(east, "foods", "rice") == 4
    assert _quantity(west, "foods", "rice") == 0
    assert _quantity(west, "fund", None) == 0


def test_fund_rejects_a_scan_and_a_subclass(inventory_session: Session) -> None:
    with pytest.raises(InventoryError, match="manually"):
        add_region_stock(
            inventory_session,
            region="east",
            category_code="fund",
            quantity=1000,
            entry_mode="scan",
        )
    with pytest.raises(InventoryError, match="subclass"):
        add_region_stock(
            inventory_session,
            region="west",
            category_code="fund",
            item_code="tshirt",
            quantity=1000,
            entry_mode="manual",
        )
    assert _quantity(region_snapshot(inventory_session, "east"), "fund", None) == 0
    assert _quantity(region_snapshot(inventory_session, "west"), "fund", None) == 0


def test_inventory_list_returns_east_then_west(inventory_session: Session) -> None:
    app.dependency_overrides[get_inventory_db] = lambda: inventory_session
    try:
        client = TestClient(app)
        for path in ("/inventory/", "/inventory"):
            response = client.get(path)
            assert response.status_code == 200
            locations = response.json()["locations"]
            assert [row["location"] for row in locations] == ["Bago East", "Bago West"]
            assert [row["region"] for row in locations] == ["east", "west"]
            assert [row["name"] for row in locations[0]["classes"]] == [
                "Fund",
                "Foods",
                "Clothing",
                "Kitchenware",
                "Utilities",
            ]
            assert locations[0]["classes"][0]["entry_mode"] == "manual_only"
            assert locations[0]["classes"][0]["items"][0]["code"] is None
    finally:
        app.dependency_overrides.pop(get_inventory_db, None)


def test_photo_loader_is_unique_and_does_not_change_stock(
    inventory_session: Session,
    tmp_path: Path,
) -> None:
    root = tmp_path / "objectDetect"
    (root / "Clothes" / "tshirt").mkdir(parents=True)
    (root / "Utility" / "soup").mkdir(parents=True)
    (root / "unassigned").mkdir()
    shared = b"same-photo"
    (root / "Clothes" / "tshirt" / "one.jpg").write_bytes(shared)
    (root / "Clothes" / "tshirt" / "copy.jpg").write_bytes(shared)
    (root / "Utility" / "soup" / "bar.jpg").write_bytes(b"soap-bar")
    (root / "unassigned" / "shelf.jpg").write_bytes(b"shelf-photo")

    catalog = tmp_path / "image_catalog.csv"
    first = load_inventory_images(inventory_session, root, catalog_csv=catalog)
    assert first["inserted"] == 3
    assert first["skipped"] == 1

    images = list(inventory_session.scalars(select(InventoryImage)))
    assert len(images) == 3
    assert all(row.confirmed_quantity == 0 for row in images)
    unassigned = next(row for row in images if row.item_code is None)
    assert unassigned.category_code is None
    soap = next(row for row in images if row.item_code == "soap")
    assert soap.category_code == "kitchenware"

    second = load_inventory_images(inventory_session, root, catalog_csv=catalog)
    assert second["inserted"] == 0
    assert second["skipped"] == 4
    assert len(list(inventory_session.scalars(select(InventoryImage)))) == 3

    catalog_text = catalog.read_text(encoding="utf-8")
    assert catalog_text.startswith("path,category_code,item_code,content_sha256,confirmed_quantity\n")
    assert catalog_text.count("\n") == 4

    quantities = list(inventory_session.scalars(select(StockBalance.quantity)))
    assert quantities
    assert all(Decimal(quantity) == 0 for quantity in quantities)


def test_receipt_stops_at_the_stock_ceiling(inventory_session: Session) -> None:
    add_region_stock(
        inventory_session,
        region="east",
        category_code="foods",
        item_code="rice",
        quantity=20000,
        entry_mode="manual",
    )
    add_region_stock(
        inventory_session,
        region="east",
        category_code="foods",
        item_code="oil",
        quantity=20000,
        entry_mode="manual",
    )
    with pytest.raises(InventoryError, match="Rice is limited to 20000"):
        add_region_stock(
            inventory_session,
            region="east",
            category_code="foods",
            item_code="rice",
            quantity=1,
            entry_mode="manual",
        )
    east = region_snapshot(inventory_session, "east")
    foods = next(row for row in east["classes"] if row["code"] == "foods")
    assert foods["quantity"] == 40_000
    assert foods["capacity"] == 60_000
    assert foods["items"][0]["capacity"] == 20000

    add_region_stock(
        inventory_session,
        region="west",
        category_code="foods",
        item_code="rice",
        quantity=20000,
        entry_mode="manual",
    )
    add_region_stock(
        inventory_session,
        region="east",
        category_code="fund",
        quantity=10_000_000_000,
        entry_mode="manual",
    )
    with pytest.raises(InventoryError, match="Fund is limited to 10000000000"):
        add_region_stock(
            inventory_session,
            region="east",
            category_code="fund",
            quantity=1,
            entry_mode="manual",
        )
    fund = next(row for row in region_snapshot(inventory_session, "east")["classes"] if row["code"] == "fund")
    assert fund["capacity"] == 10_000_000_000
    assert fund["quantity"] == 10_000_000_000


def test_seeded_depots_keep_region_labels_and_coordinates(inventory_session: Session) -> None:
    stores = list(inventory_session.scalars(select(Store).order_by(Store.region)))
    assert [(row.region, row.name) for row in stores] == [
        ("east", "Bago depot east"),
        ("west", "Pyay depot west"),
    ]
    by_region = {row.region: row for row in stores}
    for spec in STORE_SEEDS:
        store = by_region[str(spec["region"])]
        assert store.latitude == pytest.approx(float(spec["latitude"]))
        assert store.longitude == pytest.approx(float(spec["longitude"]))
        assert store.verified_at is None


def test_catalog_create_category_and_item_type(inventory_session: Session) -> None:
    create_category(
        inventory_session,
        code="medical",
        name="Medical",
        entry_mode="scan_or_manual",
    )
    create_item_type(
        inventory_session,
        category_code="medical",
        code="bandage",
        name="Bandage",
        unit="piece",
    )
    east = region_snapshot(inventory_session, "east")
    medical = next(row for row in east["classes"] if row["code"] == "medical")
    assert medical["name"] == "Medical"
    assert _quantity(east, "medical", "bandage") == 0
    add_region_stock(
        inventory_session,
        region="east",
        category_code="medical",
        item_code="bandage",
        quantity=3,
        entry_mode="manual",
    )
    assert _quantity(region_snapshot(inventory_session, "east"), "medical", "bandage") == 3


def test_demo_seed_fills_an_empty_depot_once(inventory_session: Session) -> None:
    ensure_demo_stock(inventory_session)
    assert _quantity(region_snapshot(inventory_session, "east"), "foods", "rice") == 100
    assert _quantity(region_snapshot(inventory_session, "west"), "foods", "rice") == 80
    ensure_demo_stock(inventory_session)
    assert _quantity(region_snapshot(inventory_session, "east"), "foods", "rice") == 100
