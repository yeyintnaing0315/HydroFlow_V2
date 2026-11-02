"""store daily history collected from the weather API

Revision ID: 20261017_0003
Revises: 20261015_0002
Create Date: 2026-10-17
"""
from alembic import op

from app import models  # noqa: F401
from app.db import Base

revision = "20261017_0003"
down_revision = "20261015_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["historical_days"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["historical_days"].drop(bind=bind, checkfirst=True)
