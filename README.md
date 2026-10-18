# CycleScope

Reproducible infrastructure for investigating equity-market cycles and capital
rotation. **Weeks 1–4 are implemented:** validated data ingestion, cycle analysis,
harmonic forecasts, walk-forward evaluation, and Next.js cycle and sector dashboards.
Week 2 was reimplemented after investigation of the archived model. Sector states
describe observed relative performance. No predictive market value is claimed. See [the specification](PROJECT_SPEC.md),
[agent instructions](AGENTS.md), and [milestone evidence](docs/PROGRESS.md).

The original SPY/QQQ/NVDA/MU fixture is **SYNTHETIC**: 244 invented OHLCV bars on
61 sessions per symbol, 2024-01-02 through 2024-03-28. The `synthetic_research`
profile contains 720 sessions per symbol, 2020-01-02 through 2022-11-08: the unchanged
four-symbol research fixture (2,880 bars) plus eight sector ETFs (5,760 bars),
**8,640 invented bars across 12 symbols**. Neither requires credentials.
Configured real data is never substituted with synthetic data on failure.

The corrected model recovers the synthetic signals, but **still loses to random
walk on the separately frozen 2025 SPY evaluation**. Original negative results,
corrections, and evaluation limits are documented in [methodology](docs/METHODOLOGY.md).

## Architecture

```mermaid
flowchart TD
  Sources["Synthetic fixtures / Alpaca HTTPS"] --> Adapter["Provider adapter + typed validation"]
  Adapter --> Ingest["Explicit transactional CLI ingestion"]
  Ingest --> DB[("PostgreSQL: prices + provenance")]
  DB --> Snapshot["Service: cutoff snapshot, matching feed and sessions"]
  Snapshot --> Math["Pure NumPy/SciPy: FFT, harmonic, walk-forward, sector RS"]
  Math --> Reports[("Retained inputs + immutable reports")]
  Reports --> API["FastAPI: bounded computation + versioned JSON"]
  DB --> API
  API --> Proxy["Next.js same-origin fixed-destination proxy"]
  Proxy --> UI["Cycle explorer + sector dashboard"]
```

Code lives in `src/cyclescope`: `domain`, `providers`, `services`, `storage`, `api`,
and `analytics`. Numerical functions have no provider/database I/O. Read
[engineering decisions](docs/DECISIONS.md) for boundaries and operational choices.

## Run with real Alpaca prices

For your own market-data research, use the real-data startup command below.
The separate `local_demo.sh` command deliberately uses invented offline fixtures.

Docker Desktop must be running. On your computer, create `.env` only if it does
not already exist, and open it in your editor (on macOS):

```sh
test -f .env || cp .env.example .env
open -e .env
```

Set these fields in that local file, using your own Alpaca credentials:

```dotenv
MARKET_DATA_PROVIDER=alpaca
APCA_API_KEY_ID=your_key_id
APCA_API_SECRET_KEY=your_secret_key
ALPACA_FEED=iex
```

Use `sip` only if your account has the required entitlement. Keep `.env` private;
it is ignored by Git. Credentials saved in Codex's environment do not automatically
appear on your Mac. Do not send key values in chat. Then run:

```sh
bash tools/local_alpaca.sh
```

This builds the images, checks for local credentials, migrates, downloads all 12
instruments from Alpaca, and verifies that the API serves real data from the chosen
feed. It never seeds or falls back to synthetic prices. Default history starts
2023-01-03 and ends on the last exchange session before today's New York date,
conservatively excluding a potentially incomplete current-day bar. It prints the
actual cutoff and passes it to the running web server. Reload the page: the real-
data dashboard End date and sector cutoff default to that ingested session.
The default chart/evaluation range uses the trailing 720 exchange sessions (or
the requested start if later), fitting the bounded default backtest configuration.
Ordinary startup without this setting retains the historical example date.

Subsequent refreshes can reuse built images:

```sh
bash tools/local_alpaca.sh --no-build
```

Optional `CYCLESCOPE_INGEST_START` / `CYCLESCOPE_INGEST_END` environment variables
select another covered interval. Missing sessions or unavailable feeds stop with
an error instead of inventing data. Multi-symbol ingestion is atomic per symbol;
earlier successful symbols remain if a later symbol fails. The cloud runner can
use `--cloud` for its trusted proxy build.

These are **real adjusted historical daily prices**, not continuously updating
quotes. IEX represents a single exchange's feed and can differ from consolidated
SIP prices; adjusted history can also differ from raw quote prices. Refresh is
explicit. Streaming quotes and automatic intraday updates are not implemented.

### Change dates in the dashboard

The controls show the stored date bounds and observation count for the selected
ticker and feed. Choose your dates, then select **Run analysis**. If that history
has not been downloaded, select **Download selected dates from Alpaca** first;
wait for confirmation, then run the analysis. This explicit download uses the
backend's configured credentials. Price/coverage reads never fetch upstream.

The price chart remains available for short ranges. Cycle analysis requires at
least 32 trading sessions (33 for log returns); the default lookback is 480. When
the range contains fewer observations, the page offers an explicit button to set
the lookback to the available count. Select Run analysis again afterward. There
is no silent fitting-window change. A backtest additionally needs the selected
initial training sessions plus a complete future horizon, and at most 20 folds;
the form shows the required and available counts.

Downloads accept only completed exchange sessions, conservatively excluding the
current New York day. Future-only/weekend-only ranges and feed errors return
clear failures. The supported catalog is currently SPY, QQQ, NVDA, MU and the
eight specified sector ETFs, rather than the full stock market.

## Offline demonstration with synthetic prices

With Docker Engine and Compose v2 installed, run from this checkout:

```sh
bash tools/local_demo.sh
```

This builds both nonroot containers, waits for PostgreSQL, migrates, ingests all
12 synthetic research symbols, and starts the API and dashboard. Open port 3000
in your local browser; `/` is the cycle explorer and `/sectors` is sector rotation.
Use cutoff **2022-11-08**, 480 training sessions and a 20-session horizon for the
cycle/backtest example. Sector defaults are 126/20/5. No credentials are needed.
It explicitly selects `synthetic_research`; existing real data/reports remain stored.
It does change the running API's selected profile. Restore your configured provider
with `docker compose up -d --wait --no-build api web` when finished.

The cloud runner uses writable Docker/uv caches below and
`bash tools/local_demo.sh --cloud` for its trusted proxy build. After an image build,
`--no-build` reuses the installed images. These paths were exercised here; publication
or restoration into a separate cloud task has not been tested.

## Dashboard

The dashboard provides ticker/date controls, adjusted price history, FFT spectrum
and candidate periods, future-only forecast/band/turning windows, and model versus
random-walk backtests with fold boundaries. Source labels remain visible while
scrolling. Values, fitted settings, source hashes and saved report metadata are
available as text/tables as well as charts. Replay verifies retained snapshots.
Changing analysis inputs clears stale results and cancels pending browser requests.

Start the API with the workflow below, then in a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Requires Node 24 (tested 24.19.0) and npm 11.9.0. The web service listens on port
3000; the API uses port 8000. `CYCLESCOPE_API_URL` is a **server-only** HTTP(S) origin
(default `http://127.0.0.1:8000`). The browser calls the same-origin `/backend` proxy;
Alpaca credentials belong only to the backend environment. The UI never fetches
market data automatically or substitutes fixtures for unavailable real data.
Initial date ranges are examples for the configured provider, not a guarantee of
stored coverage. The shared dashboard horizon is capped at 63 trading sessions
so forecast and evaluation use matching horizons. It uses recorded seed 17.

For a production host build, run `npm run build` then `npm run start`. The Docker
build uses Next standalone output and runs as UID 10001.

The sector page compares **XLK, XLF, XLE, XLI, XLU, XLV, XLY, XLP** with SPY.
It plots smoothed relative strength versus backward log momentum, raw normalized
history, and exact latest values. Reference/window controls invalidate stale
results. The page exposes configuration, source hashes and snapshot replay.
Each series requires the same complete sessions, provider/feed and adjusted basis.
See [sector methodology](docs/METHODOLOGY.md#sector-relative-strength--week-4).

![Synthetic sector dashboard](docs/screenshots/week4-sectors-desktop.png)

Screenshots are actual browser runs on invented fixtures. The [mobile view](docs/screenshots/week4-sectors-mobile.png)
and [cycle explorer](docs/screenshots/week4-cycles.png) show the other supported layouts.

## Local development

Prerequisites: Python 3.12, uv 0.12.23, Docker Engine and Compose v2. Run commands
from the repository root. Keep any existing `.env` rather than overwriting it.

In this cloud runner, first set writable cache locations; ordinary workstations
can omit these exports:

```sh
export DOCKER_CONFIG=/workspace/.cache/docker
export UV_CACHE_DIR=/workspace/.cache/uv
export npm_config_cache=/workspace/.cache/npm
```

```sh
cp .env.example .env  # only on first setup
uv sync --frozen
docker compose up -d --wait db
uv run alembic upgrade head
MARKET_DATA_PROVIDER=synthetic_research uv run cyclescope ingest --universe all --start 2020-01-02 --end 2022-11-08
MARKET_DATA_PROVIDER=synthetic_research uv run uvicorn cyclescope.api.app:create_app --factory --host 127.0.0.1 --port 8000
```

In a second terminal:

```sh
curl --fail 'http://127.0.0.1:8000/health'
curl --fail 'http://127.0.0.1:8000/api/v1/prices/SPY?start=2020-01-02&end=2022-11-08&limit=1000'
```

Expected: readiness `ok`, and 720 bars labeled `synthetic`. Repeating research
ingestion preserves 8,640 current research bars and appends an audit run per symbol.
`--universe core` is the default four symbols; `sectors` loads SPY plus eight ETFs,
and `all` loads all 12. Use `--symbol SPY` to load one symbol. Ingestion is atomic per symbol. Starting the
server neither migrates nor ingests automatically. Run one API process per port and
restart after changing its provider setting. For the unchanged Week 1 example,
use `MARKET_DATA_PROVIDER=synthetic` and dates 2024-01-02 through 2024-03-28.

## Container workflow

No host Python is needed for the application in this path:

```sh
docker compose up -d --wait db
docker compose build api web
docker compose run --rm api /app/.venv/bin/alembic upgrade head
docker compose run --rm -e MARKET_DATA_PROVIDER=synthetic_research api /app/.venv/bin/cyclescope ingest --universe all --start 2020-01-02 --end 2022-11-08
MARKET_DATA_PROVIDER=synthetic_research docker compose up -d --wait --no-build api web
```

The API runs as a nonroot user and ports bind to loopback. `docker compose down`
retains the PostgreSQL volume. The public sample database password is for local
development. In this cloud runner, replace only the build command with:

```sh
uv run python tools/cloud_build.py api web
```

The helper uses `compose.cloud.yml`, the runner's proxy/DNS mapping, and a trusted
CA mounted as a BuildKit secret. It preserves TLS verification.

## API contract

OpenAPI is at `/openapi.json` and interactive documentation at `/docs`.

| Route | Behavior |
| --- | --- |
| `GET /health/live` | Process liveness, independent of database |
| `GET /health` | Database/schema readiness; no upstream fetch |
| `GET /api/v1/symbols` | Supported instruments and selected provider/data kind |
| `GET /api/v1/prices/{ticker}` | Stored adjusted OHLCV for inclusive `start`/`end` |
| `GET /api/v1/prices/{ticker}/coverage` | Provider-specific stored bounds/count and latest completed session |
| `POST /api/v1/prices/{ticker}/refresh` | Explicit real Alpaca download for JSON `start`/`end`; returns audit ID and coverage |
| `GET /api/v1/cycles/{ticker}` | Training-only periodogram for `as_of` and session `lookback` |
| `POST /api/v1/forecasts/{ticker}` | Cutoff forecast, future turning windows, uncalibrated band |
| `POST /api/v1/backtests` | Rolling/expanding evaluation against matching random walk |
| `GET /api/v1/backtests/{run_id}` | Original saved backtest |
| `POST /api/v1/backtests/{run_id}/replay` | Strict replay from saved inputs/configuration |
| `GET /api/v1/analyses/{run_id}` | Original saved cycle, forecast, or backtest envelope |
| `GET /api/v1/sectors/rotation` | Observed sector/SPY strength and backward momentum |
| `GET /api/v1/sectors/runs/{run_id}` | Original saved sector report |
| `POST /api/v1/sectors/runs/{run_id}/replay` | Strict retained-input sector replay |

Tickers are uppercase; the universe is SPY, QQQ, NVDA, MU and the eight sector ETFs.
The original `synthetic` profile advertises only its four covered symbols. Prices require
both ISO dates, with ranges bounded to 3,660 calendar days within 1990–2035. `limit`
defaults to 500 (maximum 1,000); `offset` defaults to zero (maximum 100,000).
Responses include coverage, source/feed, data kind, adjustment basis, units,
snapshot hash, UTC ingestion/fetch timestamps, and ingestion-run references.

OHLC is **split/dividend-adjusted USD per share**, serialized as decimal strings.
Volume is shares; `session_date` is an exchange-session label. The locked XNYS
calendar handles holidays/extraordinary closures. Missing bars are never filled.

Errors have shape `{"error":{"code":"...","message":"...","request_id":"..."}}`
and an `X-Request-ID` header. Invalid inputs/insufficient data are 422, unknown
symbols are 404, database/provider outages are 503, and invalid provider payloads
are 502. Ingestion is CLI-only with sanitized diagnostics and nonzero error exit.
Reads never fetch upstream. Readiness does not assert valid keys or current prices.

New reports use `analysis-v2`; harmonic fits use `harmonic-increment-log-price-v2`.
Metadata retains input identity, provider/feed, configuration, package source hash,
Git revision where available, and library versions. GET preserves a legacy report's
original `analysis-v1` envelope. Strict replay returns 409 for incompatible versions,
changed input integrity, or different numerical output.

Analysis is capped at 2,520 sessions, three harmonics, 500 bootstrap draws, and 20
nonoverlapping folds. Forecast horizons are 1–126 sessions; backtests allow 1–63.
Two computations execute per API worker; saturation returns 503 `analysis_busy`.
Analysis POST bodies are limited to 64 KiB, including streamed bodies.

Sector rotation requires `as_of`; `lookback_sessions` defaults to 126 (32–1,260),
`momentum_sessions` to 20 (1–126), and `smoothing_sessions` to 5 (1–30). Defaults
require **150 consecutive sessions per symbol**, including backward warmup. The
first displayed session is the normalization reference (100), with axes at 100/0.
Ties on either axis are neutral. Missing coverage returns 422 with the affected
symbol; no interpolation or cross-feed substitution occurs. Reports use
`sectors-v1` / `sector-relative-strength-v1`, and additive migration 0003 retains
prior bars and analysis reports.

```sh
curl --fail 'http://127.0.0.1:8000/api/v1/sectors/rotation?as_of=2022-11-08&lookback_sessions=126&momentum_sessions=20&smoothing_sessions=5'
uv run python tools/run_mvp_demo.py --verify docs/experiments/synthetic-mvp-week4.json
```

The demo seeds all 12 synthetic symbols, computes all four analytic outputs and
verifies backtest/sector replay. [The recorded experiment](docs/experiments/synthetic-mvp-week4.json)
contains actual software output. Comparison ignores changing UUIDs/timestamps/audit
IDs and requires identical input hashes and numerical results with the locked runtime.

## Week 2 examples and reproducibility

With the API configured to `synthetic_research`:

```sh
curl --fail 'http://127.0.0.1:8000/api/v1/cycles/SPY?as_of=2022-11-08&lookback=480'
curl --fail -X POST 'http://127.0.0.1:8000/api/v1/forecasts/SPY' -H 'Content-Type: application/json' -d '{"as_of":"2022-11-08","lookback":480,"horizon_sessions":40,"model":{"seed":17}}'
curl --fail -X POST 'http://127.0.0.1:8000/api/v1/backtests' -H 'Content-Type: application/json' -d '{"ticker":"SPY","start":"2020-01-02","end":"2022-11-08","evaluation":{"initial_train_sessions":480,"horizon_sessions":20,"model":{"seed":17}}}'
```

Spectral candidates retain FFT-bin periods and `significance_status: not_tested`.
Harmonic fitting separately refines frequencies within bounded half-bin training
neighborhoods, then projects changes from the last observed log price. Saved origin
diagnostics expose the gap between the fitted historical curve and that price.
Turning windows are session-tolerance heuristics. Bootstrap price bands are
**uncalibrated** and omit frequency-selection/refinement uncertainty.

Reconstruct the archived failures:

```sh
uv run python tools/diagnose_week2_archive.py
```

This verifies original predictions/metrics without database or provider I/O and
writes [development diagnostics](docs/experiments/week2-diagnosis.json). It requires
the private original real report at `.local/legacy/spy-week2-v1.json` (or
`--real-report PATH`); a clean checkout must recover the original report from the
preserved archive, not refetch revised data. The public synthetic original is in
[legacy experiments](docs/experiments/legacy/synthetic-week2-v1.json).
Previously viewed outcomes used for diagnosis do not become an independent holdout.

Verify the corrected synthetic result with the locked runtime:

```sh
uv run python tools/run_demo.py --output .local/synthetic-week2-v2.json --verify docs/experiments/synthetic-week2-v2.json
```

The tool ingests synthetic SPY, computes cycles/forecast/backtest, and checks
saved-snapshot replay. Run IDs/timestamps differ between executions. Numerical
reproduction depends on the recorded runtime; arbitrary BLAS/platform changes
need not give bit-for-bit equality.

The [2025 SPY protocol](docs/experiments/spy-2025-protocol.json) froze model/source
identity before its first fetch. Its [summary](docs/experiments/spy-2025-summary.json)
records the negative result without publishing the observed target arrays. Verify
from this environment's retained private report/database without provider I/O:

```sh
(
cd /workspace/.cyclescope-recovery/week3-before-week4/extracted
UV_CACHE_DIR=/workspace/.cache/uv uv sync --frozen
MARKET_DATA_PROVIDER=alpaca ALPACA_FEED=iex UV_CACHE_DIR=/workspace/.cache/uv uv run python tools/evaluate_holdout.py verify
)
```

`freeze` and `run` created this one-time protocol/result and refuse overwrites.
A clean checkout cannot declare the already inspected interval a fresh holdout.
All real adjusted-data evaluations are retrospective, with no point-in-time
availability guarantee.

Week 4 adds Python package files and advances the package version to 0.4.0. The
strict package/library identity therefore differs from Week 2/3 even though the
forecast math is unchanged. Old GET reports still return original JSON; replay
under the new identity correctly returns 409. The command above requires the
preserved Week 3 checkout and its original installed runtime (see
[recovery instructions](docs/RECOVERY.md)); it is specific to this prepared machine.
Current demo runs replay under their own recorded identity. The older synthetic
reference also reproduces the same numerical results via `tools/run_demo.py --verify`.

## Optional real-data ingestion

Set `MARKET_DATA_PROVIDER=alpaca`, `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, and
`ALPACA_FEED=iex` (or entitled `sip`) in an ignored `.env` or secure environment.
Never commit keys. Ingestion requires HTTPS access to `data.alpaca.markets`.

The adapter requests daily `adjustment=all` bars, bounded page tokens, and explicit
IEX/SIP feed IDs. Missing keys, entitlement/rate limits, timeouts, malformed bars,
missing sessions, and invalid pagination fail clearly. IEX volume is feed-specific,
not consolidated market volume. Authenticated IEX ingestion has been verified for
SPY and all eight sector ETFs (752 sessions each over 2023–2025). SIP and real
QQQ/NVDA/MU remain untested. To explicitly load the sector universe:

```sh
MARKET_DATA_PROVIDER=alpaca ALPACA_FEED=iex uv run cyclescope ingest --universe sectors --start 2023-01-03 --end 2025-12-31
```

Real demo cutoff is **2025-12-31**, a stored historical example, not current prices.
The inclusive end-of-day correction is
retained: Alpaca receives the requested New York date's final microsecond rather
than next midnight. Offline tests require no private keys or paid services.

## Tests and quality checks

Integration tests require a **disposable** database whose name ends in `_test`.
They migrate/truncate it and exercise downgrade/upgrade. Preserve other databases.

```sh
docker compose exec -T db createdb -U cyclescope cyclescope_test  # once
export TEST_DATABASE_URL=postgresql+psycopg://cyclescope:cyclescope@localhost:5432/cyclescope_test
uv run pytest --cov=cyclescope --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run alembic check
```

Without PostgreSQL, `uv run pytest -m 'not postgres'` runs numerical/domain/provider/
configuration tests. Skipped database tests do not validate end-to-end acceptance.
GitHub Actions uses disposable PostgreSQL without private credentials.

```sh
uv run python tools/generate_fixtures.py
uv run python tools/generate_research_fixtures.py --output .local/research-check.csv
uv run python tools/generate_sector_fixtures.py --output .local/sectors-check.csv
```

## Frontend checks and browser tests

```sh
cd frontend
npm ci
npm run lint
npm run format:check
npm run typecheck
npm run test
npm run build
```

Generated TypeScript contracts are checked in. Regenerate without a running API:

```sh
uv run python tools/export_openapi.py  # from repository root
npm --prefix frontend run generate:api
```

Browser tests use a separate `cyclescope_ui_test` PostgreSQL database, migrate it,
and load the 12-symbol synthetic research fixture. They start owned API/web
processes on ports 8011/3001 and stop them afterward, preserving main data. Build
first with `npm --prefix frontend run build`, then from the repository root:

```sh
PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium uv run python tools/run_frontend_e2e.py
```

The shown Chromium path is available in this cloud runner. On another machine,
install Playwright Chromium (`npx playwright install --with-deps chromium` from
`frontend`) and omit that environment variable. Optional `UI_TEST_DATABASE_URL`
must name a disposable database ending `_ui_test`; its user needs database-creation
permission only if the database does not already exist. Tests never use market
credentials. Logs go to `.local/e2e-*.log`; failure traces/screenshots and successful
fixture screenshots go to ignored `frontend/test-results/`. CI runs the same
workflow without private keys, checks generated-contract drift, and retains failures.

## Validation and remaining work

**227 tests passed with 98% backend statement coverage**, no skipped tests, in the
full PostgreSQL run. Ruff lint/format, strict mypy and Alembic model parity passed.
Regression checks cover nonaligned/off-grid signals, cutoff isolation, origin
anchoring, ridge-bootstrap centering, metric denominators, workload bounds and
legacy reports. The nonroot 0.4.0 API and web containers passed readiness and
the complete local synthetic workflow.

The synthetic v2 RMSE was 0.003701 versus random walk 0.035222. On the separately
frozen 2025 real SPY interval, v2 RMSE was **0.031729 versus random walk 0.028150**.
The model still lost on real data. Errors are natural-log price; details and MAE are
in [methodology](docs/METHODOLOGY.md). Passing software tests does not establish
financial usefulness.

Current frontend validation: **23 unit tests and 16 Chromium browser tests passed**,
including actual API metrics, cycle/forecast and sector charts, saved replay, loading,
cancellation, empty/error/invalid-date states, and mobile overflow/keyboard checks.
Strict TypeScript, frontend lint/format, API regeneration, and production build
passed. The Week 2 forecast algorithms and frozen result files are unchanged.

The full npm dependency audit, including development packages, reports zero known
vulnerabilities. The locked Starlette test client emits one upstream HTTPX
deprecation warning. Hosted GitHub Actions and public deployment have not been
observed; the fully functional local demo is the Week 4 delivery path. Measured
latencies and reproduction commands are in [performance notes](docs/PERFORMANCE.md).
P0 engineering acceptance is covered locally. P1 work such as calibrated intervals,
additional baselines, significance testing, background jobs and hosting remains future work.
