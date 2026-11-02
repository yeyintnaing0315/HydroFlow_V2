"""Long-range hydrology provider limits (Open-Meteo archive, NASA POWER, GloFAS)."""

from __future__ import annotations

from datetime import date

# NASA POWER daily point data (AG community) is commonly used from the early 1980s.
NASA_POWER_START = date(1981, 1, 1)
# Open-Meteo GloFAS consolidated reanalysis (river_discharge).
GLOFAS_DISCHARGE_START = date(1984, 1, 1)
# Open-Meteo ERA5 archive for rainfall / 2 m met.
OPEN_METEO_ARCHIVE_START = date(1940, 1, 1)

# Product floor for date picker and hindcast scoring (2010-present rebuild).
APP_HISTORY_START = date(2010, 1, 1)

# Timeline scoring needs discharge; provider archives extend further back.
HISTORY_START = APP_HISTORY_START
