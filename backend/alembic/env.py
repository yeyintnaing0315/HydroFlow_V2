from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from app import models  # noqa: F401
from app.db import DATABASE_URL, Base
from app.models import (  # noqa: F401
    AllocationLine,
    AllocationPlan,
    DeliveryRoute,
    DetectionObject,
    DetectionSession,
    FloodLabel,
    PredictionRun,
    RouteStop,
    StockBalance,
    StockMovement,
    Store,
    TownshipForecast,
    TownshipStaticFeatures,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    return os.getenv("DATABASE_URL") or DATABASE_URL


def run_migrations_offline() -> None:
    url = _database_url()
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _database_url()
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {"connect_timeout": 5}
    migration_engine = create_engine(url, connect_args=connect_args)
    try:
        with migration_engine.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        migration_engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
