"""add separate Bago East and Bago West stock tables

Revision ID: 20261018_0005
Revises: 20261017_0004
Create Date: 2026-10-18

The live schema no longer maps these tables. This revision keeps the historical
upgrade path self-contained so a later revision can copy the rows and drop them.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "20261018_0005"
down_revision = "20261017_0004"
branch_labels = None
depends_on = None


def _balance_table(name: str, prefix: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_code", sa.String(length=40), nullable=False),
        sa.Column("item_code", sa.String(length=40), nullable=True),
        sa.Column("quantity", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.CheckConstraint("quantity >= 0", name=f"ck_{prefix}_balance_nonnegative"),
        sa.CheckConstraint(
            "(category_code <> 'fund') OR (item_code IS NULL)",
            name=f"ck_{prefix}_fund_has_no_subclass",
        ),
        sa.CheckConstraint(
            "(category_code = 'fund') OR (item_code IS NOT NULL)",
            name=f"ck_{prefix}_subclass_required",
        ),
    )
    op.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{prefix}_balance_item "
            f"ON {name} (category_code, item_code) WHERE item_code IS NOT NULL"
        )
    )
    op.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{prefix}_balance_fund "
            f"ON {name} (category_code) WHERE item_code IS NULL"
        )
    )


def _movement_table(name: str, prefix: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_code", sa.String(length=40), nullable=False),
        sa.Column("item_code", sa.String(length=40), nullable=True),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("entry_mode", sa.String(length=20), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name=f"ck_{prefix}_movement_quantity"),
        sa.CheckConstraint("direction IN ('in', 'out')", name=f"ck_{prefix}_movement_direction"),
        sa.CheckConstraint(
            "entry_mode IN ('manual', 'scan')",
            name=f"ck_{prefix}_movement_entry_mode",
        ),
        sa.CheckConstraint(
            "(category_code <> 'fund') OR (entry_mode = 'manual' AND item_code IS NULL)",
            name=f"ck_{prefix}_fund_manual_only",
        ),
        sa.CheckConstraint(
            "(category_code = 'fund') OR (item_code IS NOT NULL)",
            name=f"ck_{prefix}_movement_subclass_required",
        ),
    )


def create_legacy_region_tables() -> None:
    bind = op.get_bind()
    existing = set(inspect(bind).get_table_names())
    if "bago_east_balances" not in existing:
        _balance_table("bago_east_balances", "bago_east")
    if "bago_west_balances" not in existing:
        _balance_table("bago_west_balances", "bago_west")
    if "bago_east_movements" not in existing:
        _movement_table("bago_east_movements", "bago_east")
    if "bago_west_movements" not in existing:
        _movement_table("bago_west_movements", "bago_west")


def seed_legacy_region_balances(connection) -> None:
    from app.services.inventory import ITEM_TYPES

    for table in ("bago_east_balances", "bago_west_balances"):
        present = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        if present:
            continue
        for category_code, types in ITEM_TYPES.items():
            for code, _name, unit, _order in types:
                connection.execute(
                    text(
                        f"INSERT INTO {table} (category_code, item_code, quantity, unit) "
                        "VALUES (:category_code, :item_code, 0, :unit)"
                    ),
                    {"category_code": category_code, "item_code": code, "unit": unit},
                )
        connection.execute(
            text(
                f"INSERT INTO {table} (category_code, item_code, quantity, unit) "
                "VALUES ('fund', NULL, 0, 'mmk')"
            )
        )


def upgrade() -> None:
    create_legacy_region_tables()
    seed_legacy_region_balances(op.get_bind())


def downgrade() -> None:
    for name in (
        "bago_west_movements",
        "bago_east_movements",
        "bago_west_balances",
        "bago_east_balances",
    ):
        op.drop_table(name)
