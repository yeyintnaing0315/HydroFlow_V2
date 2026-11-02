"""Road-cost cache. Writes commit on this file only."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Float, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.cache.sqlite import resolve_cache_path, sqlite_engine

CACHE_ENV = "ROAD_CACHE"
CACHE_RELATIVE = "data/cache/road_cache.sqlite"


class RoadCacheBase(DeclarativeBase):
    pass


class TravelEdge(RoadCacheBase):
    __tablename__ = "travel_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_id: Mapped[str] = mapped_column(String(160), index=True)
    to_id: Mapped[str] = mapped_column(String(160), index=True)
    distance_m: Mapped[float] = mapped_column(Float)
    duration_s: Mapped[float] = mapped_column(Float)
    crosses_floodplain: Mapped[bool] = mapped_column(Boolean)
    geometry: Mapped[dict] = mapped_column(JSON, nullable=False)


def cache_path():
    return resolve_cache_path(CACHE_ENV, CACHE_RELATIVE)


def road_engine():
    return sqlite_engine(cache_path(), RoadCacheBase.metadata)


def insert_travel_edge(
    *,
    from_id: str,
    to_id: str,
    distance_m: float,
    duration_s: float,
    crosses_floodplain: bool,
    geometry: dict,
) -> None:
    """Insert one edge. This session is not the operational session."""
    with Session(road_engine()) as session:
        session.add(
            TravelEdge(
                from_id=from_id,
                to_id=to_id,
                distance_m=distance_m,
                duration_s=duration_s,
                crosses_floodplain=crosses_floodplain,
                geometry=geometry,
            )
        )
        session.commit()


def list_travel_edges() -> list[dict[str, object]]:
    with Session(road_engine()) as session:
        rows = session.scalars(select(TravelEdge).order_by(TravelEdge.id)).all()
        return [
            {
                "from_id": row.from_id,
                "to_id": row.to_id,
                "distance_m": row.distance_m,
                "duration_s": row.duration_s,
                "crosses_floodplain": bool(row.crosses_floodplain),
                "geometry": row.geometry,
            }
            for row in rows
        ]
