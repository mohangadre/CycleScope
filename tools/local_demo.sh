#!/usr/bin/env bash
# Explicit offline profile; existing real rows and saved reports are preserved.
set -euo pipefail
cd "$(dirname "$0")/.."
build_mode=standard
if [[ $# -gt 1 ]]; then
  echo "Usage: bash tools/local_demo.sh [--cloud|--no-build]" >&2
  exit 2
fi
case "${1:-}" in
  --cloud) build_mode=cloud ;;
  --no-build) build_mode=none ;;
  "") ;;
  *) echo "Usage: bash tools/local_demo.sh [--cloud|--no-build]" >&2; exit 2 ;;
esac
export MARKET_DATA_PROVIDER=synthetic_research
export NEXT_TELEMETRY_DISABLED=1
docker compose up -d --wait db
if [[ $build_mode == standard ]]; then
  docker compose build api web
elif [[ $build_mode == cloud ]]; then
  uv run python tools/cloud_build.py api web
fi
docker compose run --rm api /app/.venv/bin/alembic upgrade head
docker compose run --rm api /app/.venv/bin/cyclescope ingest --universe all --start 2020-01-02 --end 2022-11-08
docker compose up -d --wait --no-build api web
echo "SYNTHETIC demo ready: web port 3000, API port 8000, sector page /sectors."
echo "No market data was fetched. Real-provider rows and historical reports were preserved."
