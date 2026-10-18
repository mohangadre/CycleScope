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

## Real-data startup correction

The original `local_demo.sh` instructions intentionally started invented fixtures;
they were insufficient for a user expecting real Alpaca prices. Added a separately
named, explicit real-data startup/refresh command with secure local key setup in
README. It ingests all 12 supported instruments, fails rather than falling back,
and verifies real feed/final-session coverage. The latest-day calculation uses
the locked exchange calendar and excludes today's potentially incomplete bar.

The real workflow was exercised through 2026-10-16 on IEX for all 12 instruments,
including QQQ/NVDA/MU. This supersedes the earlier milestone's limited live-symbol
verification. It does not establish SIP entitlement or streaming quote support.
The cloud runtime requires host ingestion through its supported proxy; the
`--cloud` command handles that, while Docker Desktop uses container ingestion.

The web server receives the actual ingestion cutoff and trailing 720-session
start date at runtime. Real-source controls now open on that range rather than
the old 2025 example. Synthetic examples keep their original fixture dates. Added
a browser regression for runtime real-source controls without mocking prices.
Historical data, model mathematics and negative evaluation results are preserved.

Validation after the startup correction: frontend lint/format, strict types,
production host/container builds, 21 unit tests and 13 Chromium tests passed.
Missing local credentials were checked to fail explicitly before ingestion.
Python production numerical/API code is unchanged by this correction; the prior
215-test backend regression evidence remains applicable.

## Date-range usability correction

Added provider-specific stored coverage and an explicit browser download action
for a selected real Alpaca range. The API reuses validated ingestion and retained
audit snapshots; it rejects invalid, future-only and empty-session ranges before
network access. The two-job workload limit and 64 KiB streamed-body limit also
cover downloads. Provider entitlement/rate-limit failures remain visible without
synthetic fallback. Supported tickers remain the documented 12-instrument catalog.

The dashboard now shows available bounds/count and retains observed-price charts
for ranges too short for the selected lookback. Users can explicitly set the
available lookback and rerun; fewer than 32/33 sessions remain price-only. Backtest
controls show their training-plus-horizon sample requirement. No numerical
forecasting algorithm or favorable/unfavorable recorded result was changed.

Validation: **227 backend tests, 98% coverage, no skips; 23 frontend unit tests and
16 Chromium browser tests passed**, plus lint/format, strict types and production
host/container builds. Actual fixture tests cover shorter dates through forecast
and backtest, source-specific coverage when changing tickers, and visible download
errors. Real IEX was also exercised from the browser through the host API: QQQ
2022-01-03–2022-12-30 downloaded 251 real observations, rendered prices, and produced
cycles/forecast after an explicit 251-session lookback choice. Only metadata and
failure cases are mocked in browser tests; no invented prices are shown as real
market evidence.

An additional real-storage smoke check covered all 12 IEX tickers: 252 daily
observations over 2024, a separate five-session range in March 2025, and
cutoff-matched 126-session cycles/forecasts. All responses retained real provenance
and matching final observed prices. This checks application behavior, not forecast
accuracy. The four outputs of the full synthetic experiment also reproduced
their recorded input hashes/numerical results exactly; new saved replay passed.

Adding Python transport/coverage files changes package-wide source identity.
Historical report retrieval is preserved; strict replay across that source change
continues to reject incompatible identities. Current freshly computed reports
replay with their own recorded environment. The full synthetic numerical reference
comparison remains a separate verification from historical strict replay.
