"""rename foods item code can to canned_fish

Revision ID: 20261028_0007
Revises: 20261027_0006
Create Date: 2026-10-28
"""

from alembic import op
from sqlalchemy import inspect, text

revision = "20261028_0007"
down_revision = "20261027_0006"
branch_labels = None
depends_on = None

_ITEM_CODE_TABLES = (
    "stock_balances",
    "stock_movements",
    "inventory_images",
    "detection_objects",
    "allocation_lines",
)


def _table_exists(bind, name: str) -> bool:
    return name in inspect(bind).get_table_names()


def _has_column(bind, table: str, column: str) -> bool:
    return any(item["name"] == column for item in inspect(bind).get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "inventory_item_types"):
        op.execute(
            text(
                """
                UPDATE inventory_item_types
                SET code = 'canned_fish', name = 'Canned fish'
                WHERE code = 'can'
                  AND category_id IN (
                      SELECT id FROM inventory_categories WHERE code = 'foods'
                  )
                """
            )
        )
    for table in _ITEM_CODE_TABLES:
        if not _table_exists(bind, table) or not _has_column(bind, table, "category_code"):
            continue
        op.execute(
            text(
                f"""
                UPDATE {table}
                SET item_code = 'canned_fish'
                WHERE category_code = 'foods' AND item_code = 'can'
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "inventory_item_types"):
        op.execute(
            text(
                """
                UPDATE inventory_item_types
                SET code = 'can', name = 'Can'
                WHERE code = 'canned_fish'
                  AND category_id IN (
                      SELECT id FROM inventory_categories WHERE code = 'foods'
                  )
                """
            )
        )
    for table in _ITEM_CODE_TABLES:
        if not _table_exists(bind, table) or not _has_column(bind, table, "category_code"):
            continue
        op.execute(
            text(
                f"""
                UPDATE {table}
                SET item_code = 'can'
                WHERE category_code = 'foods' AND item_code = 'canned_fish'
                """
            )
        )
