"""replace east/west stock tables and add forecast, plan, and detection tables

Revision ID: 20261027_0006
Revises: 20261018_0005
Create Date: 2026-10-27
"""
from alembic import op
from sqlalchemy import inspect, text

from app import models  # noqa: F401
from app.db import Base

revision = "20261027_0006"
down_revision = "20261018_0005"
branch_labels = None
depends_on = None

NEW_TABLES = (
    "stores",
    "township_static_features",
    "prediction_runs",
    "township_forecasts",
    "flood_labels",
    "allocation_plans",
    "allocation_lines",
    "detection_sessions",
    "detection_objects",
    "stock_balances",
    "stock_movements",
    "delivery_routes",
    "route_stops",
)

LEGACY_TABLES = (
    "bago_east_movements",
    "bago_west_movements",
    "bago_east_balances",
    "bago_west_balances",
)


def _seed_stores(connection) -> None:
    from app.services.inventory import STORE_SEEDS

    for spec in STORE_SEEDS:
        connection.execute(
            text(
                "INSERT INTO stores (region, name, latitude, longitude) "
                "SELECT :region, :name, :latitude, :longitude "
                "WHERE NOT EXISTS (SELECT 1 FROM stores WHERE region = :region)"
            ),
            spec,
        )


def _copy_legacy(connection) -> None:
    names = set(inspect(connection).get_table_names())
    pairs = (
        ("bago_east_balances", "bago_east_movements", "east"),
        ("bago_west_balances", "bago_west_movements", "west"),
    )
    for balance_table, movement_table, region in pairs:
        if balance_table in names:
            connection.execute(
                text(
                    "INSERT INTO stock_balances (store_id, category_code, item_code, quantity, unit) "
                    f"SELECT s.id, b.category_code, b.item_code, b.quantity, b.unit "
                    f"FROM {balance_table} AS b "
                    "JOIN stores AS s ON s.region = :region"
                ),
                {"region": region},
            )
        if movement_table in names:
            connection.execute(
                text(
                    "INSERT INTO stock_movements ("
                    "store_id, category_code, item_code, direction, entry_mode, "
                    "quantity, note, created_at"
                    ") "
                    "SELECT s.id, m.category_code, m.item_code, m.direction, m.entry_mode, "
                    "m.quantity, m.note, m.created_at "
                    f"FROM {movement_table} AS m "
                    "JOIN stores AS s ON s.region = :region"
                ),
                {"region": region},
            )


def _seed_missing_balances(connection) -> None:
    from app.services.inventory import ITEM_TYPES

    stores = connection.execute(text("SELECT id FROM stores")).all()
    for (store_id,) in stores:
        for category_code, types in ITEM_TYPES.items():
            for code, _name, unit, _order in types:
                connection.execute(
                    text(
                        "INSERT INTO stock_balances "
                        "(store_id, category_code, item_code, quantity, unit) "
                        "SELECT :store_id, :category_code, :item_code, 0, :unit "
                        "WHERE NOT EXISTS ("
                        "SELECT 1 FROM stock_balances "
                        "WHERE store_id = :store_id AND category_code = :category_code "
                        "AND item_code = :item_code)"
                    ),
                    {
                        "store_id": store_id,
                        "category_code": category_code,
                        "item_code": code,
                        "unit": unit,
                    },
                )
        connection.execute(
            text(
                "INSERT INTO stock_balances "
                "(store_id, category_code, item_code, quantity, unit) "
                "SELECT :store_id, 'fund', NULL, 0, 'mmk' "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM stock_balances "
                "WHERE store_id = :store_id AND category_code = 'fund' "
                "AND item_code IS NULL)"
            ),
            {"store_id": store_id},
        )


def _drop_legacy() -> None:
    bind = op.get_bind()
    names = set(inspect(bind).get_table_names())
    for name in LEGACY_TABLES:
        if name in names:
            op.drop_table(name)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    for name in NEW_TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)
    _seed_stores(bind)
    _copy_legacy(bind)
    _seed_missing_balances(bind)
    _drop_legacy()


def downgrade() -> None:
    import importlib.util
    from pathlib import Path

    legacy_path = Path(__file__).with_name("20261018_0005_region_stock.py")
    spec = importlib.util.spec_from_file_location("legacy_region_stock_0005", legacy_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the legacy stock revision")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    bind = op.get_bind()
    module.create_legacy_region_tables()
    names = set(inspect(bind).get_table_names())
    if "stock_balances" in names and "stores" in names:
        for table, region in (("bago_east_balances", "east"), ("bago_west_balances", "west")):
            bind.execute(
                text(
                    f"INSERT INTO {table} (category_code, item_code, quantity, unit) "
                    "SELECT b.category_code, b.item_code, b.quantity, b.unit "
                    "FROM stock_balances AS b "
                    "JOIN stores AS s ON s.id = b.store_id "
                    "WHERE s.region = :region"
                ),
                {"region": region},
            )
    if "stock_movements" in names and "stores" in names:
        for table, region in (("bago_east_movements", "east"), ("bago_west_movements", "west")):
            bind.execute(
                text(
                    f"INSERT INTO {table} ("
                    "category_code, item_code, direction, entry_mode, quantity, note, created_at"
                    ") "
                    "SELECT m.category_code, m.item_code, m.direction, m.entry_mode, "
                    "m.quantity, m.note, m.created_at "
                    "FROM stock_movements AS m "
                    "JOIN stores AS s ON s.id = m.store_id "
                    "WHERE s.region = :region"
                ),
                {"region": region},
            )
    for name in reversed(NEW_TABLES):
        op.drop_table(name)
