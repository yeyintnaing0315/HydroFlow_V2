"""add utility dipper inventory item type

Revision ID: 20261029_0008
Revises: 20261028_0007
Create Date: 2026-10-29
"""

from alembic import op
from sqlalchemy import inspect, text

revision = "20261029_0008"
down_revision = "20261028_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if "inventory_item_types" not in inspect(bind).get_table_names():
        return
    op.execute(
        text(
            """
            INSERT INTO inventory_item_types (category_id, code, name, unit, sort_order)
            SELECT c.id, 'dipper', 'Water dipper', 'piece', 13
            FROM inventory_categories AS c
            WHERE c.code = 'utility'
              AND NOT EXISTS (
                  SELECT 1 FROM inventory_item_types AS t
                  WHERE t.category_id = c.id AND t.code = 'dipper'
              )
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "inventory_item_types" not in inspect(bind).get_table_names():
        return
    op.execute(
        text(
            """
            DELETE FROM inventory_item_types
            WHERE code = 'dipper'
              AND category_id IN (SELECT id FROM inventory_categories WHERE code = 'utility')
            """
        )
    )
