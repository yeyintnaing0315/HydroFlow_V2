"""SQLite cache files. Each file has its own engine and its own transaction."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine

PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENGINES: dict[str, Engine] = {}


def resolve_cache_path(env_name: str, default_relative: str) -> Path:
    raw = os.getenv(env_name)
    if not raw:
        return PROJECT_ROOT / default_relative
    path = Path(raw)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path


def sqlite_engine(path: Path, metadata: MetaData) -> Engine:
    resolved = path.resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    key = str(resolved)
    engine = _ENGINES.get(key)
    if engine is None:
        engine = create_engine(
            "sqlite:///" + resolved.as_posix(),
            connect_args={"check_same_thread": False},
        )
        metadata.create_all(engine)
        _ENGINES[key] = engine
    return engine
