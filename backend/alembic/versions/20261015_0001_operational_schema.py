"""baseline legacy tables and add operational audit schema

Revision ID: 20261015_0001
Revises:
Create Date: 2026-10-15
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import inspect, text

from app import models  # noqa: F401
from app.db import Base

revision = "20261015_0001"
down_revision = None
branch_labels = None
depends_on = None

NEW_TABLES = (
    "risk_results",
    "job_runs",
    "model_versions",
    "inundation_products",
    "official_warnings",
    "provider_observations",
    "admin_aliases",
    "admin_areas",
    "dataset_versions",
    "data_sources",
)


def upgrade() -> None:
    """Adopt existing V1 databases without dropping or rewriting legacy rows."""
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)
    indexes = {item["name"] for item in inspect(bind).get_indexes("locations")}
    if "uq_location_name" not in indexes:
        op.create_index("uq_location_name", "locations", ["name"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    available = set(inspect(bind).get_table_names())
    for table_name in NEW_TABLES:
        if table_name in available:
            Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)
