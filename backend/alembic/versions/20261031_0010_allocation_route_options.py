"""store allocation plan context and township route options

Revision ID: 20261031_0010
Revises: 20261029_0009
Create Date: 2026-10-31
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20261031_0010"
down_revision = "20261029_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "allocation_plans" in tables:
        columns = {column["name"] for column in inspector.get_columns("allocation_plans")}
        if "plan_context" not in columns:
            op.add_column("allocation_plans", sa.Column("plan_context", sa.JSON(), nullable=True))
    if "township_route_options" not in tables:
        op.create_table(
            "township_route_options",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("plan_id", sa.Integer(), nullable=False),
            sa.Column("township_id", sa.String(length=80), nullable=False),
            sa.Column("option_index", sa.Integer(), nullable=False),
            sa.Column("selected", sa.Boolean(), nullable=False),
            sa.Column("recommended", sa.Boolean(), nullable=False),
            sa.Column("routing_method", sa.String(length=40), nullable=False),
            sa.Column("flood_exposure", sa.String(length=20), nullable=False),
            sa.Column("distance_m", sa.Float(), nullable=True),
            sa.Column("duration_s", sa.Float(), nullable=True),
            sa.Column("rainfall_mm", sa.Float(), nullable=True),
            sa.Column("discharge_m3_s", sa.Float(), nullable=True),
            sa.Column("blocked_segments", sa.JSON(), nullable=True),
            sa.Column("geometry", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["plan_id"], ["allocation_plans.id"], ondelete="CASCADE"),
            sa.UniqueConstraint(
                "plan_id",
                "township_id",
                "option_index",
                name="uq_township_route_option",
            ),
        )
        op.create_index("ix_township_route_options_plan_id", "township_route_options", ["plan_id"])
        op.create_index("ix_township_route_options_township_id", "township_route_options", ["township_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "township_route_options" in tables:
        op.drop_index("ix_township_route_options_township_id", table_name="township_route_options")
        op.drop_index("ix_township_route_options_plan_id", table_name="township_route_options")
        op.drop_table("township_route_options")
    if "allocation_plans" in tables:
        columns = {column["name"] for column in inspector.get_columns("allocation_plans")}
        if "plan_context" in columns:
            op.drop_column("allocation_plans", "plan_context")
