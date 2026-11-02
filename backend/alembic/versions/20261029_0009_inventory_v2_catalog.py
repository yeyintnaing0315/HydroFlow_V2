"""inventory v2 five-class catalog restructure

Revision ID: 20261029_0009
Revises: 20261029_0008
Create Date: 2026-10-29
"""

from alembic import op
from sqlalchemy import inspect, text

revision = "20261029_0009"
down_revision = "20261029_0008"
branch_labels = None
depends_on = None

_KITCHENWARE_CODES = (
    "bowl",
    "knife",
    "mug",
    "spoon",
    "soap",
    "plate",
    "pot",
    "cup",
    "dipper",
)
def _table_exists(bind, name: str) -> bool:
    return name in inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "inventory_categories"):
        return

    # Category renames on catalog and operational string keys.
    for stmt in (
        "UPDATE inventory_categories SET code = 'clothing', name = 'Clothing' WHERE code = 'clothes'",
        "UPDATE inventory_categories SET code = 'utilities', name = 'Utilities' WHERE code = 'utility'",
        "UPDATE stock_balances SET category_code = 'clothing' WHERE category_code = 'clothes'",
        "UPDATE stock_balances SET category_code = 'utilities' WHERE category_code = 'utility'",
        "UPDATE stock_movements SET category_code = 'clothing' WHERE category_code = 'clothes'",
        "UPDATE stock_movements SET category_code = 'utilities' WHERE category_code = 'utility'",
        "UPDATE inventory_images SET category_code = 'clothing' WHERE category_code = 'clothes'",
        "UPDATE inventory_images SET category_code = 'utilities' WHERE category_code = 'utility'",
    ):
        op.execute(text(stmt))

    op.execute(
        text(
            """
            INSERT INTO inventory_categories (code, name, entry_mode, sort_order)
            SELECT 'kitchenware', 'Kitchenware', 'scan_or_manual', 4
            WHERE NOT EXISTS (
                SELECT 1 FROM inventory_categories WHERE code = 'kitchenware'
            )
            """
        )
    )

    for order, code in enumerate(("fund", "foods", "clothing", "kitchenware", "utilities"), start=1):
        op.execute(
            text("UPDATE inventory_categories SET sort_order = :order WHERE code = :code").bindparams(
                order=order,
                code=code,
            )
        )

    # Clothing subclass renames.
    for stmt in (
        """
        UPDATE inventory_item_types SET code = 'm_longyi', name = 'Men longyi'
        WHERE code = 'm_cloth'
          AND category_id IN (SELECT id FROM inventory_categories WHERE code = 'clothing')
        """,
        """
        UPDATE inventory_item_types SET code = 'f_longyi', name = 'Women longyi'
        WHERE code = 'f_cloth'
          AND category_id IN (SELECT id FROM inventory_categories WHERE code = 'clothing')
        """,
        "UPDATE stock_balances SET item_code = 'm_longyi' WHERE category_code = 'clothing' AND item_code = 'm_cloth'",
        "UPDATE stock_balances SET item_code = 'f_longyi' WHERE category_code = 'clothing' AND item_code = 'f_cloth'",
        "UPDATE stock_movements SET item_code = 'm_longyi' WHERE category_code = 'clothing' AND item_code = 'm_cloth'",
        "UPDATE stock_movements SET item_code = 'f_longyi' WHERE category_code = 'clothing' AND item_code = 'f_cloth'",
        "UPDATE inventory_images SET item_code = 'm_longyi' WHERE category_code = 'clothing' AND item_code = 'm_cloth'",
        "UPDATE inventory_images SET item_code = 'f_longyi' WHERE category_code = 'clothing' AND item_code = 'f_cloth'",
    ):
        op.execute(text(stmt))

    # Utilities: netbed -> bednet.
    for stmt in (
        """
        UPDATE inventory_item_types SET code = 'bednet', name = 'Bed net'
        WHERE code = 'netbed'
          AND category_id IN (SELECT id FROM inventory_categories WHERE code = 'utilities')
        """,
        "UPDATE stock_balances SET item_code = 'bednet' WHERE category_code = 'utilities' AND item_code = 'netbed'",
        "UPDATE stock_movements SET item_code = 'bednet' WHERE category_code = 'utilities' AND item_code = 'netbed'",
        "UPDATE inventory_images SET item_code = 'bednet' WHERE category_code = 'utilities' AND item_code = 'netbed'",
    ):
        op.execute(text(stmt))

    # Move kitchenware SKUs to kitchenware category in catalog.
    codes = ", ".join(f"'{code}'" for code in _KITCHENWARE_CODES)
    op.execute(
        text(
            f"""
            UPDATE inventory_item_types AS t
            SET category_id = (SELECT id FROM inventory_categories WHERE code = 'kitchenware')
            WHERE t.code IN ({codes})
              AND t.category_id = (SELECT id FROM inventory_categories WHERE code = 'utilities')
            """
        )
    )

    # cup -> water_dipper in catalog.
    op.execute(
        text(
            """
            UPDATE inventory_item_types SET code = 'water_dipper', name = 'Water dipper'
            WHERE code = 'cup'
              AND category_id = (SELECT id FROM inventory_categories WHERE code = 'kitchenware')
            """
        )
    )

    # Stock: split utility rows to kitchenware category for kitchen SKUs.
    op.execute(
        text(
            f"""
            UPDATE stock_balances
            SET category_code = 'kitchenware'
            WHERE category_code = 'utilities'
              AND item_code IN ({codes})
            """
        )
    )
    op.execute(
        text(
            """
            UPDATE stock_balances SET item_code = 'water_dipper'
            WHERE category_code = 'kitchenware' AND item_code = 'cup'
            """
        )
    )

    if _table_exists(bind, "stock_balances"):
        from decimal import Decimal

        from sqlalchemy.orm import Session

        with Session(bind=bind) as merge_session:
            dippers = merge_session.execute(
                text(
                    """
                    SELECT id, store_id, quantity FROM stock_balances
                    WHERE category_code = 'kitchenware' AND item_code = 'dipper'
                    """
                )
            ).fetchall()
            for dipper_id, store_id, dipper_qty in dippers:
                qty = Decimal(str(dipper_qty))
                target = merge_session.execute(
                    text(
                        """
                        SELECT id, quantity FROM stock_balances
                        WHERE store_id = :store_id
                          AND category_code = 'kitchenware'
                          AND item_code = 'water_dipper'
                        """
                    ),
                    {"store_id": store_id},
                ).fetchone()
                if target is not None:
                    target_id, target_qty = target[0], Decimal(str(target[1]))
                    merge_session.execute(
                        text("UPDATE stock_balances SET quantity = :qty WHERE id = :id"),
                        {"qty": target_qty + qty, "id": target_id},
                    )
                    merge_session.execute(
                        text("DELETE FROM stock_balances WHERE id = :id"),
                        {"id": dipper_id},
                    )
                else:
                    merge_session.execute(
                        text(
                            """
                            UPDATE stock_balances SET item_code = 'water_dipper'
                            WHERE id = :id
                            """
                        ),
                        {"id": dipper_id},
                    )
            merge_session.commit()

    op.execute(
        text(
            f"""
            UPDATE stock_movements
            SET category_code = 'kitchenware'
            WHERE category_code = 'utilities'
              AND item_code IN ({codes})
            """
        )
    )
    op.execute(
        text(
            """
            UPDATE stock_movements SET item_code = 'water_dipper'
            WHERE category_code = 'kitchenware' AND item_code IN ('cup', 'dipper')
            """
        )
    )
    op.execute(
        text(
            f"""
            UPDATE inventory_images
            SET category_code = 'kitchenware'
            WHERE category_code = 'utilities'
              AND item_code IN ({codes})
            """
        )
    )
    op.execute(
        text(
            """
            UPDATE inventory_images SET item_code = 'water_dipper'
            WHERE category_code = 'kitchenware' AND item_code IN ('cup', 'dipper')
            """
        )
    )

    # Drop dipper catalog row; ensure water_dipper exists.
    op.execute(
        text(
            """
            DELETE FROM inventory_item_types
            WHERE code = 'dipper'
              AND category_id = (SELECT id FROM inventory_categories WHERE code = 'kitchenware')
            """
        )
    )
    op.execute(
        text(
            """
            INSERT INTO inventory_item_types (category_id, code, name, unit, sort_order)
            SELECT c.id, 'water_dipper', 'Water dipper', 'piece', 6
            FROM inventory_categories AS c
            WHERE c.code = 'kitchenware'
              AND NOT EXISTS (
                  SELECT 1 FROM inventory_item_types AS t
                  WHERE t.category_id = c.id AND t.code = 'water_dipper'
              )
            """
        )
    )

    op.execute(
        text(
            """
            DELETE FROM inventory_item_types
            WHERE category_id = (SELECT id FROM inventory_categories WHERE code = 'utilities')
              AND code NOT IN ('bednet', 'blanket', 'towel', 'box')
            """
        )
    )

    # Delete orphan stock rows for removed SKUs.
    op.execute(
        text(
            """
            DELETE FROM stock_balances
            WHERE category_code = 'utilities'
              AND item_code IS NOT NULL
              AND item_code NOT IN ('bednet', 'blanket', 'towel', 'box')
            """
        )
    )

    from app.services.inventory import seed_catalog, seed_regions

    session = op.get_bind()
    # Alembic bind may not be ORM Session; use connection via Sessionmaker
    from sqlalchemy.orm import Session

    with Session(bind=bind) as orm_session:
        seed_catalog(orm_session)
        seed_regions(orm_session)
        orm_session.commit()


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "inventory_categories"):
        return
    # Irreversible split without manual data restore; no-op downgrade.
    pass
