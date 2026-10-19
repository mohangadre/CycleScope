#!/usr/bin/env bash
# Fetch real adjusted daily bars; never seed or fall back to synthetic prices.
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v docker >/dev/null 2>&1; then
  echo 'Docker CLI not found. On Mac, install Docker Desktop and enable its CLI tools.' >&2
  exit 1
fi
if [[ $# -gt 1 ]]; then
  echo 'Usage: bash tools/local_alpaca.sh [--cloud|--no-build]' >&2
  exit 2
fi
case "${1:-}" in
  --cloud) build_mode=cloud ;;
  --no-build) build_mode=none ;;
  '') build_mode=standard ;;
  *) echo 'Usage: bash tools/local_alpaca.sh [--cloud|--no-build]' >&2; exit 2 ;;
esac
export MARKET_DATA_PROVIDER=alpaca
export NEXT_TELEMETRY_DISABLED=1
docker compose up -d --wait db
if [[ $build_mode == standard ]]; then
  docker compose build api web
elif [[ $build_mode == cloud ]]; then
  uv run python tools/cloud_build.py api web
fi
docker compose run --rm -T api /app/.venv/bin/python - <<'PY'
from cyclescope.config import Settings
settings = Settings()
if not settings.apca_api_key_id or not settings.apca_api_secret_key:
    raise SystemExit(
        'Missing Alpaca credentials on THIS computer. Set APCA_API_KEY_ID and '
        'APCA_API_SECRET_KEY in the repository .env file. Do not paste keys into chat.'
    )
print(f'Selected real Alpaca feed: {settings.alpaca_feed}. No synthetic fallback.')
PY
docker compose run --rm api /app/.venv/bin/alembic upgrade head
as_of=${CYCLESCOPE_INGEST_END:-}
if [[ -z $as_of ]]; then
  as_of=$(docker compose run --rm -T api /app/.venv/bin/python - <<'PY'
from datetime import UTC, datetime
from cyclescope.domain.calendar import completed_session_before_today
# Conservatively exclude today's possibly incomplete daily bar, including after close.
print(completed_session_before_today(datetime.now(UTC)).isoformat())
PY
)
fi
start=${CYCLESCOPE_INGEST_START:-2023-01-03}
echo "Downloading all 12 instruments from Alpaca: $start through $as_of."
if [[ $build_mode == cloud ]]; then
  # Cloud proxy-backed credentials/networking belong to the host execution context.
  uv run cyclescope ingest --universe all --start "$start" --end "$as_of"
else
  docker compose run --rm api /app/.venv/bin/cyclescope ingest --universe all --start "$start" --end "$as_of"
fi
export CYCLESCOPE_DEFAULT_AS_OF=$as_of
dashboard_start=$(docker compose run --rm -T api /app/.venv/bin/python - "$start" "$as_of" <<'PY'
from datetime import date
import sys
from cyclescope.domain.calendar import trailing_sessions
# A 720-session default fits 480 training sessions plus twelve 20-session folds.
print(max(date.fromisoformat(sys.argv[1]), trailing_sessions(date.fromisoformat(sys.argv[2]), 720)[0]))
PY
)
export CYCLESCOPE_DEFAULT_START=$dashboard_start
docker compose up -d --wait --no-build api web
docker compose exec -T api /app/.venv/bin/python - "$as_of" <<'PY'
import json
import sys
from urllib.parse import urlencode
from urllib.request import urlopen
from cyclescope.config import Settings
from cyclescope.domain.models import CATALOG
expected = f'alpaca-{Settings().alpaca_feed}'
def get(path):
    with urlopen('http://127.0.0.1:8000' + path, timeout=10) as response:
        return json.load(response)
health = get('/health')
if health['provider'] != expected or health['data_kind'] != 'real':
    raise SystemExit('API is not serving the selected real Alpaca feed')
for instrument in CATALOG:
    query = urlencode({'start': sys.argv[1], 'end': sys.argv[1]})
    result = get(f'/api/v1/prices/{instrument.symbol}?{query}')
    if (
        result['provider'] != expected or result['data_kind'] != 'real'
        or result['total'] != 1 or len(result['bars']) != 1
        or result['bars'][0]['session_date'] != sys.argv[1]
    ):
        raise SystemExit(f'Latest real coverage verification failed: {instrument.symbol}')
print(f'Verified {len(CATALOG)} real instruments on {sys.argv[1]}, source {expected}.')
PY
echo "REAL daily-data app ready: web port 3000; source Alpaca; observed through $as_of."
echo "Dashboard defaults to $dashboard_start through $as_of; sector cutoff $as_of. Reload the page."
echo 'Daily OHLCV is split/dividend-adjusted, not a streaming quote. Re-run this command to refresh.'
