#!/bin/sh
set -eu

alembic upgrade head
python -m app.cli seed-sources >/dev/null
if [ -d /data/geography ] && ls /data/geography/*.geojson >/dev/null 2>&1; then
  python -m app.cli import-geography /data/geography/*.geojson >/dev/null
fi

exec "$@"
