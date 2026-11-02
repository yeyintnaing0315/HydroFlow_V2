import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Column, Table, create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import NullPool


class Base(DeclarativeBase):
    pass


class OperationalDatabaseError(RuntimeError):
    """PostgreSQL is configured, but the operational database cannot be opened."""


_project_db = (Path(__file__).resolve().parents[2] / "hydroflow.db").as_posix()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_project_db}")
INVENTORY_DATABASE_URL = os.getenv("INVENTORY_DATABASE_URL", DATABASE_URL)


def _is_postgresql_url(url: str) -> bool:
    scheme = url.split(":", 1)[0].lower()
    return scheme == "postgres" or scheme == "postgresql" or scheme.startswith("postgresql+")


def _safe_database_target(url: str) -> str:
    """Host and database only, so a connection error does not echo the password."""
    try:
        parsed = make_url(url)
    except Exception:
        return "postgresql"
    port = f":{parsed.port}" if parsed.port else ""
    database = f"/{parsed.database}" if parsed.database else ""
    return f"{parsed.drivername}://{parsed.host or ''}{port}{database}"


def _build_engine(url: str) -> Engine:
    if _is_postgresql_url(url):
        return create_engine(
            url,
            connect_args={"connect_timeout": 5},
            pool_pre_ping=True,
        )
    return create_engine(
        url,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )


engine = _build_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
inventory_engine = _build_engine(INVENTORY_DATABASE_URL)
InventorySession = sessionmaker(bind=inventory_engine, autoflush=False, expire_on_commit=False)


REQUIRED_TABLES = {
    "locations",
    "observations",
    "alerts",
    "data_sources",
    "dataset_versions",
    "admin_areas",
    "admin_aliases",
    "settlements",
    "provider_observations",
    "official_warnings",
    "inundation_products",
    "exposure_summaries",
    "model_versions",
    "job_runs",
    "risk_results",
    "historical_days",
    "stores",
    "stock_balances",
    "stock_movements",
    "township_static_features",
    "prediction_runs",
    "township_forecasts",
    "flood_labels",
    "allocation_plans",
    "allocation_lines",
    "delivery_routes",
    "route_stops",
    "detection_sessions",
    "detection_objects",
}


def schema_status() -> dict[str, object]:
    """Report migration readiness without changing or deleting user data."""
    available = set(inspect(engine).get_table_names())
    missing = sorted(REQUIRED_TABLES - available)
    revision = None
    if "alembic_version" in available:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return {
        "ready": not missing,
        "missing_tables": missing,
        "revision": revision,
    }


def ensure_operational_connection(url: str | None = None) -> None:
    """Open a PostgreSQL operational URL, or raise. Never substitute SQLite."""
    target = DATABASE_URL if url is None else url
    if not _is_postgresql_url(target):
        return
    probe = create_engine(
        target,
        connect_args={"connect_timeout": 3},
        pool_pre_ping=True,
    )
    try:
        with probe.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise OperationalDatabaseError(
            "DATABASE_URL points at PostgreSQL, but the operational database is unreachable. "
            "HydroFlow will not store operational history in SQLite. "
            f"{_safe_database_target(target)}: {type(exc).__name__}: {exc}"
        ) from exc
    finally:
        probe.dispose()


def _ensure_model_columns(bind: Engine) -> None:
    """Add nullable columns that models declare but an older database lacks.

    ``create_all`` never alters an existing table. A local database created
    before ``allocation_plans.plan_context`` was added otherwise raises
    ``no such column`` on every plan read.
    """
    from sqlalchemy.exc import OperationalError

    from app import models  # noqa: F401

    inspector = inspect(bind)
    inspector.clear_cache()
    existing = set(inspector.get_table_names())
    pending: list[tuple[Table, Column[object]]] = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue
        present = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present or column.primary_key:
                continue
            if getattr(column, "computed", None) is not None:
                continue
            if not column.nullable and column.server_default is None:
                continue
            pending.append((table, column))
    if not pending:
        inspector.clear_cache()
        return
    with bind.begin() as connection:
        dialect = connection.dialect
        preparer = dialect.identifier_preparer
        for table, column in pending:
            statement = text(
                f"ALTER TABLE {preparer.quote(table.name)} "
                f"ADD COLUMN {preparer.quote(column.name)} "
                f"{column.type.compile(dialect=dialect)}"
            )
            try:
                connection.execute(statement)
            except OperationalError as exc:
                message = str(exc).lower()
                if "duplicate column" in message or "already exists" in message:
                    continue
                raise
    inspector.clear_cache()


def create_tables() -> None:
    """Test/development helper; deployments must run Alembic migrations."""
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
    _ensure_model_columns(engine)


def init_operational_database() -> None:
    """Connect to the configured operational database, then create tables.

    A PostgreSQL URL that cannot be opened stops startup. It is not rewritten
    to the SQLite file used by tests and local defaults.
    """
    ensure_operational_connection(DATABASE_URL)
    if INVENTORY_DATABASE_URL != DATABASE_URL:
        ensure_operational_connection(INVENTORY_DATABASE_URL)
    create_tables()


def drop_tables() -> None:
    from app import models  # noqa: F401

    Base.metadata.drop_all(engine)


def _open_session(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    yield from _open_session(SessionLocal)


def get_inventory_db() -> Generator[Session, None, None]:
    yield from _open_session(InventorySession)
