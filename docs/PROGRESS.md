# Milestone evidence

## Week 1 — Data and backend

- [x] Python 3.12 installable package, uv lock, Docker Compose and nonroot API image.
- [x] Provider-neutral typed data model; explicit synthetic/real provenance.
- [x] Synthetic SPY/QQQ/NVDA/MU fixture and bounded Alpaca IEX/SIP adapter.
- [x] Complete-session validation, idempotent PostgreSQL ingestion, retained snapshots.
- [x] Alembic migrations, health/liveness, symbols, paginated prices, OpenAPI/errors.
- [x] Provider/domain/API/CLI/PostgreSQL tests and migration round-trip.

After the requested Week 2 rollback, Week 1 passed **78 tests**, no skipped database
tests, **99% statement coverage**, Ruff lint/format, strict mypy and model parity.
All 3,877 price bars and 35 ingestion audit records were preserved. The rebuilt
nonroot Week 1 image served real IEX SPY data and the original synthetic workflow.
This records the rollback baseline, not the current implementation's test count.

The inclusive Alpaca end-of-day correction remains a Week 1 adapter fix with a
regression assertion. Authenticated IEX reads are verified; SIP and other symbols
were not live-tested. No hosted GitHub Actions execution has been observed.

## Week 2 — Diagnosis and reimplementation

The user authorized reimplementation after inspection of the rollback archive at
`/workspace/.cyclescope-recovery/week2-rollback-6144a953f450`, which remains untouched.
The [original synthetic report](experiments/legacy/synthetic-week2-v1.json) is public;
the original real report remains private at `.local/legacy/spy-week2-v1.json`.
[Diagnostics](experiments/week2-diagnosis.json) reconstruct saved predictions/metrics
and preserve unfavorable evidence.

Diagnosis found a large fitted-versus-observed origin gap in real SPY projections,
coarse FFT-bin periods that degraded off-grid extrapolation, and a ridge-bootstrap
centering defect. Cutoff isolation and random-walk metric denominators were correct.
Origin anchoring changes the forecast contract to conditional fitted increments;
it carries the observed terminal residual forward and is an explicit modeling
assumption, not a universal correction to unconditional regression.

- [x] Inspect archive and reconstruct original negative results.
- [x] Verify FFT normalization, signal recovery, and invalid-input checks.
- [x] Test training-only bounded frequency refinement on nonaligned analytic signals.
- [x] Test conditional-origin increments and ridge-centered residual-change bootstrap.
- [x] Verify future turning windows, walk-forward folds, baselines and cutoff isolation.
- [x] Verify analysis APIs, migration preservation, raw legacy GET and strict replay.
- [x] Reproduce versioned v2 synthetic report exactly with the locked runtime.
- [x] Freeze the new 2025 SPY protocol before fetching/scoring; preserve negative result.
- [x] Complete full PostgreSQL, lint/format/type, migration parity and container checks.

The Week 2 software 0.2.1 uses `analysis-v2` and `harmonic-increment-log-price-v2`.
Legacy GET preserves original JSON; incompatible strict replay returns 409. The
full suite passed **175 tests with 98% statement coverage**, no skips, and one
upstream Starlette test-client deprecation warning. Ruff lint/format, strict mypy
and Alembic parity passed. Numerical tests include off-grid periods, nonaligned
sample lengths, origin invariance, bootstrap centering and refinement fallbacks.

The nonroot UID 10001 image built, passed schema readiness and real cycle/forecast
HTTP checks, and exactly replayed host synthetic and 2025 real saved reports.
Synthetic reference reproduction and real snapshot replay use retained inputs;
they do not silently refetch latest prices. Current real SPY storage covers 1,003
sessions, 2022–2025; earlier ingestion snapshots remain available.

Synthetic v2 RMSE was 0.003701 versus baseline 0.035222 (12 folds/240 targets).
The new fixed 2025 real SPY result **still lost to random walk**: RMSE
0.031729 versus 0.028150; MAE 0.021545 versus 0.020625 (12 folds/240 targets,
ten terminal sessions unscored). Previously viewed 2022–2024 and synthetic results
remain development diagnostics. See [methodology](METHODOLOGY.md) and the
[frozen protocol](experiments/spy-2025-protocol.json).

Uncalibrated bands, untested spectral significance, later-adjusted data limitations,
and negative findings remain explicit. No market edge, significance, profitability
or generalization claim follows from Week 2 engineering acceptance.

## Week 3 — Dashboard and user workflow

- [x] Next.js 16 / React 19 dashboard with strict TypeScript and locked dependencies.
- [x] Ticker/date/lookback/horizon controls and explicit preprocessing settings.
- [x] Interactive observed-price, FFT spectrum, and future forecast/band charts.
- [x] Trading-session cutoff, candidate turning windows and accessible value tables.
- [x] Walk-forward baseline metrics, fold boundaries, metadata and saved replay.
- [x] Persistent source labels; significance, uncertainty and adjusted-data caveats.
- [x] Loading, empty, invalid-input and unavailable-provider states with request IDs.
- [x] Request cancellation and stale-result invalidation when selection changes.
- [x] Same-origin fixed-destination proxy; no browser provider secrets or data refresh.
- [x] Production build, generated API contracts, container and CI integration.
- [x] Fixture browser journey, error/cancellation states and mobile/keyboard smoke tests.

Verified locally: **16 unit tests, 8 Chromium browser tests**, frontend lint/format,
strict typing and production build. Browser success paths use the actual
PostgreSQL-backed synthetic API, comparing displayed metrics with returned values;
only failure/empty/loading scenarios intercept responses. Three SVG charts and
saved replay are checked. The UI test database is separate from main/backend-test
storage; the runner stops only the processes it starts. Screenshots/traces are
retained under ignored `frontend/test-results/`.

Backend regression remains **175 tests passing, 98% statement coverage**, plus
Ruff, strict mypy and migration parity. Generated API contracts regenerate with
identical hashes. Numerical source and the frozen Week 2 reports are unchanged.
The production dependency audit is clean; an unpatched development-only lint glob
advisory is documented in DECISIONS.md. Hosted CI/public deployment are unverified.

## Week 4 — Sector analysis and polish

- [x] Eight documented sector ETFs / SPY, exact matching sessions/feed/adjustments.
- [x] Pure log-ratio normalization, trailing smoothing/momentum and quadrant rules.
- [x] Neutral boundary states, explicit units, window bounds and no future input.
- [x] Sector API, retained-input reports/replay and additive migration 0003.
- [x] Sector dashboard with reference controls, quadrant/history charts and values.
- [x] Complete deterministic sector fixtures; original stock fixtures unchanged.
- [x] Authenticated IEX ingestion for SPY plus all eight ETFs, 2023–2025.
- [x] Mathematical, PostgreSQL, transport, browser and migration tests.
- [x] Reproducible full MVP experiment and one-command local demo script.
- [x] Architecture diagram, method/recovery/limitations docs and actual screenshots.
- [x] Measured local HTTP performance, with raw timings and hardware/runtime notes.
- [x] CI definitions for backend, frontend, generated schemas, audit and demo reproduction.

Version 0.4.0 retains forecast model `harmonic-increment-log-price-v2` unchanged.
There are 40 new Python sector tests (26 mathematical/domain, 14 database/API),
bringing the full backend to **215 passing tests, 98% statement coverage**, no skips.
Ruff lint/format, strict mypy and Alembic parity passed. The one remaining warning
is the upstream Starlette test-client HTTPX deprecation.

Frontend checks passed: **21 unit tests and 12 Chromium browser tests**, lint,
format, strict typing and production build. Actual fixture success paths compare
sector ratios, indexes and quadrants to the returned report and verify saved replay.
Two sector charts, error behavior, changed-window invalidation and mobile overflow
are exercised alongside the original eight cycle-dashboard tests. An initial
chart-count selector included legend icon SVGs; it was narrowed to the two main
chart canvases. Screenshots were captured from successful runs and visually inspected.

The full npm audit is now clean, including development packages. The vulnerable
lint preset chain was replaced with maintained ESLint/TypeScript/Hooks tooling;
framework runtime versions remain unchanged. See [decisions](DECISIONS.md).

The original 244 stock fixture bars and 2,880 core research bars retain their
bytes. A separate 5,760-bar sector file expands research to **8,640 bars / 12
symbols**. Explicit `--universe` choices preserve the four-symbol default.
Real storage retains 1,003 SPY sessions over 2022–2025 and adds 752 sessions per
sector over 2023–2025; earlier ingestion snapshots remain. SIP and real QQQ/NVDA/MU
are unverified. The production real-data sector page was exercised in Chromium:
all eight ratios matched stored prices, source labels were correct and saved
replay passed. Real-data screenshots remain private under `.local/`.

[The full synthetic experiment](experiments/synthetic-mvp-week4.json) reproduces
all four input hashes and numerical outputs with the locked runtime; backtest and
sector strict replay pass. The older synthetic v2 numerical reference also matches.
The preserved Week 3 checkout/runtime verifies the frozen real SPY protocol and
exact original snapshot replay after new ingestion. New package files/version
change global source identity: historical GET is unchanged and current-code strict
replay correctly returns 409 for those older runs. See [recovery](RECOVERY.md).

The original unfavorable real SPY result remains **RMSE 0.031729 versus random
walk 0.028150**. There is no predictive market claim, calibrated interval,
significance test, sector-rotation forecast or point-in-time data guarantee.

Both nonroot production containers run locally with health checks. The explicit
synthetic demo was started through `tools/local_demo.sh`; the configured IEX
profile is restored afterward. [Performance notes](PERFORMANCE.md) describe
measured request latency and a price-query projection improvement. No hosted
GitHub Actions run, public deployment or separate-task restoration is claimed.

P0 acceptance is demonstrated locally. Public hosting is optional under Week 4's
local-demo alternative. P1 enhancements remain separate work: calibrated uncertainty,
stronger baselines, significance/event scoring, queues/caching when justified,
and hosting with operational/authentication controls.
