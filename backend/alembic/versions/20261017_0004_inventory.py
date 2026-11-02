"""add inventory catalog tables

Revision ID: 20261017_0004
Revises: 20261017_0003
Create Date: 2026-10-17
"""
from alembic import op
from sqlalchemy.orm import Session

from app import models  # noqa: F401
from app.db import Base
from app.services.inventory import seed_catalog

revision = "20261017_0004"
down_revision = "20261017_0003"
branch_labels = None
depends_on = None

TABLES = (
    "inventory_categories",
    "inventory_item_types",
    "inventory_images",
)


def upgrade() -> None:
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)
    session = Session(bind=bind)
    seed_catalog(session)
    session.flush()
    session.close()


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
