from typing import Literal

from pydantic import BaseModel, Field


class DatabaseHealth(BaseModel):
    ready: bool
    missing_tables: list[str] = Field(default_factory=list)
    revision: str | None = None


class ModelHealth(BaseModel):
    flood: bool
    help: bool
    allocation: bool
    object_detect: bool = False


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    database: DatabaseHealth | None = None
    models: ModelHealth | None = None
