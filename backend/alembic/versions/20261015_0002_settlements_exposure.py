"""add separately typed settlements and exposure summaries

Revision ID: 20261015_0002
Revises: 20261015_0001
Create Date: 2026-10-15
"""
from alembic import op

from app import models  # noqa: F401
from app.db import Base

revision = "20261015_0002"
down_revision = "20261015_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["settlements"].create(bind=bind, checkfirst=True)
    Base.metadata.tables["exposure_summaries"].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["exposure_summaries"].drop(bind=bind, checkfirst=True)
    Base.metadata.tables["settlements"].drop(bind=bind, checkfirst=True)
