from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.services import clients


@pytest.mark.asyncio
async def test_resolve_prefers_default_model_over_empty_consolidated(monkeypatch) -> None:
    start, end = date(2026, 7, 1), date(2026, 7, 3)

    async def fake_range(lat, lon, s, e, *, models):
        if models is None:
            return {
                date(2026, 7, 1): 1.0,
                date(2026, 7, 2): 2.0,
                date(2026, 7, 3): 3.0,
            }
        return {date(2026, 7, 1): None, date(2026, 7, 2): None, date(2026, 7, 3): None}

    monkeypatch.setattr(clients, "_glofas_discharge_date_range", fake_range)
    monkeypatch.setattr(clients, "glofas_daily_discharge", AsyncMock(return_value=[]))

    rows = await clients.resolve_glofas_discharge_daily(0.0, 0.0, start, end)
    assert rows == [(date(2026, 7, 1), 1.0), (date(2026, 7, 2), 2.0), (date(2026, 7, 3), 3.0)]
