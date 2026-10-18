# Engineering decisions

## Typed backend and explicit ingestion

Use an installable `src/cyclescope` package. Provider adapters perform HTTP/file I/O;
domain models validate values/units; services orchestrate; SQLAlchemy describes
persistence; FastAPI handles transport; analytics contains pure numerical functions.
No Redis or worker service is needed for bounded daily-data requests.

Use PostgreSQL for development and integration tests. Alembic owns schema changes;
the API never creates tables or seeds data on startup. Explicit CLI ingestion is
atomic per symbol/request. A multi-symbol invocation commits symbols independently;
later failure exits nonzero while retaining earlier successful symbols.

Store adjusted OHLC as `NUMERIC(22,8)` and serialize decimal strings. All OHLC in a
series has the same split/dividend-adjusted basis. Alpaca requests `adjustment=all`;
IEX and SIP have distinct provider IDs. USD and the initial four-symbol universe are
explicit. The supported US equities/ETFs share the XNYS full-day session schedule;
this is not a universal exchange-calendar mapping.

Retain each successful ingestion's normalized payload, provider/feed version,
requested interval, timestamps and SHA-256. Latest bars upsert by symbol/session/
provider/basis and reference the last ingestion. Identical ingestion preserves
current values/counts while appending an audit run. Earlier snapshots survive
revisions. Snapshots are append-only by application convention, not administrator-
proof storage. Analysis reports retain their own selected inputs.

## Bounded provider requests and calendar validation

The real adapter uses a fixed HTTPS destination, ten-second timeouts, at most 20
pages, 8 MiB per page and 4,000 bars. Redirects/retries are disabled. Missing keys,
access denial, rate limits, timeouts, malformed bars, pagination loops, duplicates
and missing sessions fail explicitly. No synthetic substitution occurs. Strict
complete-range ingestion means requesting smaller known-covered intervals for
IPO/halt/history gaps; prices are never interpolated.

`exchange-calendars` handles holidays/extraordinary closures over 1990–2035 rather
than weekday or 252/365 arithmetic. Future announcements can revise calendars, so
the dependency version and observed session dates remain explicit. Price reads use
one provider/basis and a repeatable-read transaction for consistent counts/pages/
coverage. Health checks test database/schema readiness, not upstream availability.

Alpaca's `end` is inclusive. Request the end date's New York `23:59:59.999999` rather
than the following midnight, which can include an unwanted next-day bar. This
Week 1 adapter correction and its outgoing-parameter regression test survive
rollback/reimplementation. IEX SPY ingestion is verified; SIP/other symbols are not.

## Reproducibility and deployment boundary

`uv.lock` pins dependencies/artifact hashes. Container base images are digest-pinned
and run as a nonroot UID. The optional cloud build helper uses the existing proxy,
resolves it for Docker, and mounts the trusted CA as a build secret. TLS remains
verified; the CA is not copied into the image. Standard Compose has no cloud-specific
requirement. Runtime commands use installed binaries without resolving or rebuilding
dependencies at startup. Ports bind to loopback; the supplied password is a public
local-development default. Public hosting/authentication are outside this milestone.

## Week 2 numerical contracts

Declare NumPy directly and add SciPy for detrending, peak detection and bounded
frequency optimization, with dev-only stubs for strict typing. No ML framework is
needed. Pure analytics accepts `PriceSeries` plus typed configuration. Filter to
the cutoff before validation, logs, detrending, selection/refinement, fit or bootstrap;
backtests physically pass only each training slice to the forecasting function.

Retain the normalized FFT periodogram and its coarse bin candidates. Refine
frequencies separately with training-only bounded variable projection in half-bin
neighborhoods clipped by valid period/repetition bounds. Fit at most three harmonics
to log adjusted close with an unpenalized intercept, scaled linear trend and ridge.
The augmented-system SVD pseudoinverse supports zero penalty and rank deficiency.
Record refinement convergence/fallback, bounds, objectives, initial/fitted periods
and evaluation count; do not imply increased FFT resolution.

The v1 global-level extrapolation was often far from the latest observed SPY
price. V2 projects conditional fitted increments:
`last_log + fitted(T+h) - fitted(T)`. Persist observed/fitted origin and adjustment
so the boundary is auditable. This carries the observed terminal residual forward
and changes the prediction contract; unconditional regression is legitimate, and
anchoring does not establish predictive market value. Nonaligned analytic signal
tests address the original reliance on favorable bin-aligned examples.

Correct the ridge bootstrap by sampling coefficient deviations as
`beta + A @ residual_noise`, rather than refitting `X @ beta` and shrinking the fit
again. Anchor each path using fitted and sampled residual changes from the origin.
Circular residual blocks retain short dependence. Bands remain exploratory and
uncalibrated, conditional on fixed selected/refined frequencies; no coverage or
full selection-uncertainty claim is made. Turning windows are a separate heuristic.

## Versioned persistence and workload limits

`analysis_runs` stores the versioned response, normalized request, selected adjusted-
close snapshot/hash, source references, creation time and software identity. JSON
columns preserve coefficients, periods, fold boundaries, targets and metric
denominators within this bounded milestone. Additive migration 0002 preserves
Week 1 tables/data; no numerical-method change requires rewriting its schema.

New software 0.2.1 produces `analysis-v2` with
`harmonic-increment-log-price-v2`. GET returns stored JSON unchanged, including
legacy v1 reports. Strict replay checks schema/model compatibility before applying
current configuration defaults, then verifies input/source/library identity and
outputs. A mismatch returns 409. Value-identical re-ingestion does not alter input
identity merely because audit IDs change. Code hashes cover actual package Python
files, including uncommitted development work, not just Git SHA.

Keep synchronous computation in FastAPI's thread pool, bounded to two jobs per
worker, 2,520 observations, 20 nonoverlapping folds, three harmonics, 500 bootstrap
draws and 64 KiB analysis bodies including streamed content. Saturation is 503.
Explicit frequency-optimization budgets prevent an unbounded solver workload.

## Preserve negative evidence and separate evaluation roles

Do not overwrite the rollback archive or original unfavorable experiment reports.
The public synthetic report and private real report retain original bytes; publish
only derived real-data diagnostic/provenance summaries, not observed target arrays.
Reconstruction/ablations of the old synthetic and 2022–2024 market outcomes are
labeled reused development data. Diagnose model-boundary and numerical defects
with analytic tests rather than retuning against those outcomes.

Freeze the 2025 retrospective SPY configuration, source identity and runner hash
before acquiring/scoring its targets, and retain an exclusive attempt marker.
Refuse to overwrite/rescore an attempted protocol; verify saved inputs instead.
The corrected model still lost on the new interval, and the result remains visible.
One symbol/year on later-adjusted data establishes no point-in-time, significance,
calibrated coverage or trading claim. The inspected 2025 outcomes are now development
data for any future changes, not a reusable untouched holdout.

Queues, extra baselines, statistical significance, calibrated intervals, turning-
point scoring and strategy simulation remain separate enhancements.


## Week 3: typed browser workflow without changing the numerical engine

Use Next.js App Router, React, strict TypeScript and Recharts. Browser components
render server-produced results; they do not reimplement FFT, fitting, calendars,
backtest scoring or uncertainty. Generate types from a deterministic offline
OpenAPI export and check drift in CI. TypeScript 5.9 satisfies the generator's
supported peer range. Keep Python numerical source unchanged so Week 2 snapshots
and strict replay retain the same model/code identity.

The runtime server proxy accepts only supported API paths/methods and a fixed
server-configured origin. It bounds streamed POST bodies to 64 KiB, limits upstream
time, forwards sanitized API errors/request IDs, and disables caching. Provider
credentials stay outside the frontend. No CORS, browser-side credentials,
provider-specific requests or automatic ingestion are required. Reject arbitrary
proxy destinations and paths; the configurable origin belongs to the operator.

Load all requested price pages up to 2,520 sessions; reject changing provenance,
duplicates and inconsistent pagination. Fetch the analysis's cycles/forecast from
matching snapshots and show failures explicitly. Abort browser requests and clear
stale results on analysis-input changes. Aborting a browser request does not
promise cancellation of already-running bounded backend computation. Backtest-only
settings invalidate backtests while retaining valid observed/forecast panels.

Price/forecast dates are category axes of supplied exchange sessions. No weekend
samples or calendar interpolation are invented. Join the projected line at the
last observed cutoff, show future bounds/heuristic windows separately, and keep
source labels visible. Text tables support inspection without interpreting color.
Pooled MAE/RMSE use log-price units, and direction scoring explains the zero-return
tie category. No inferred trading or significance claim appears in the dashboard.

Build the web container with digest-pinned Node 24 and Next standalone output;
serve installed artifacts as nonroot UID 10001 without runtime package downloads.
Host builds use ordinary Next output. Compose connects web to the internal API;
only loopback ports are published. The cloud helper extends its existing trusted
proxy/CA setup to web builds, without disabling TLS or copying credentials/CA into
the runtime image.

Browser tests use a dedicated *_ui_test database and actual fixture API. The
runner creates/migrates/seeds this database, starts owned servers on separate
ports, preserves test exit status, and stops those servers in a finally block.
Success tests inspect real returned metrics and replay; mocks target failure and
race scenarios. Production UI and browser checks are reproducible without private
keys. Tests do not establish accessibility conformance across every assistive
technology or browser; Chromium desktop/mobile smoke checks are the current scope.

## Week 4: complete matched sector histories and retained observations

Keep the specification's eight-ETF universe explicit and compute price ratios
against SPY on one complete, matching session grid. Use trailing mean log ratios,
reference-normalized indexes and backward differences, with documented neutral
ties. These are descriptive observations, separate from the harmonic forecast.
No provider or storage access occurs in the numerical function. The service loads
one repeatable-read panel and persists both the selected inputs and response.

Add migration 0003 for `sector_runs`; do not rewrite older analysis rows, migrations
or fixtures. Keep the original 61-session synthetic provider and core research
bytes unchanged. A separate deterministic sector file extends only the research
profile. CLI defaults still ingest the original four symbols; explicit `sectors`
and `all` choices make the larger request reviewable and reproducible.

The shared two-job API semaphore also bounds sector computation/replay. Fixed
window/universe limits bound output and work. The same-origin browser proxy adds
only the three supported sector paths; it remains a fixed server destination with
body/time limits. Charts use supplied session dates; shared-session validation
protects history joins by array index. Exact values and neutral states remain
available as text, independent of chart colors.

Global package hashing is intentionally conservative: adding Python modules or
changing package metadata invalidates strict replay identity for older reports.
Keep the old checkout/runtime for those reports rather than weaken identity checks.
The Week 3 archive and database dump were created before Week 4 changes; recovery
verification uses its own virtual environment. Current synthetic numerical
reference comparison and new-report strict replay are separate checks.

## Frontend lint dependency hardening

Week 3's complete audit exposed an unpatched `braces` stack-exhaustion advisory
(GHSA-vfj7-8cjw-p6xm) through the Next lint preset's glob chain. Week 4 removes
that development-only preset and uses maintained ESLint 10, typescript-eslint,
the standard JavaScript rules, and the React Hooks plugin, whose peer range
explicitly supports ESLint 10. The linter no longer includes Next-specific or
React JSX style rules; strict TypeScript, Hooks checks, actual browser tests and
Next production builds remain required. No runtime framework downgrade, audit
suppression or forced incompatible dependency resolution was used.

The full npm audit, including development dependencies, now reports zero known
vulnerabilities. CI audits the locked dependency tree. This records the observed
audit result; future advisories can require maintenance.

## Measured price-read projection

Week 4 latency measurement found repeated decoding/transfer of the full retained
ingestion JSON payload for every price row in an ORM join. Load only ingestion
metadata needed by the response, while preserving prices and source fields.
Existing PostgreSQL/API/browser tests validate compatibility; before/after raw
HTTP timings are retained in [performance notes](PERFORMANCE.md). This is a
measured query correction, not an added caching or background-job architecture.

## Explicit real-data startup

Keep the offline fixture demo explicit and provide `tools/local_alpaca.sh` for
normal Alpaca use. The latter forces the real provider, checks credential presence
without printing values, ingests all 12 supported instruments, and verifies the
served feed and final session before announcing success. It never substitutes
invented prices. Keys must be configured separately on each computer; Codex's
network-secret bindings do not transfer to a Mac checkout.

Default ingestion stops at the exchange session on/before yesterday in New York,
conservatively excluding a current-day partial bar. Re-running explicitly refreshes
the stored daily data. The cloud helper's `--cloud` path uses the host's supported
proxy-backed ingestion context; ordinary Docker Desktop uses container ingestion.
Strict gap validation remains unchanged.

The helper supplies public start/end defaults to the web container. Next renders
the two pages dynamically so those values are read at startup/request time rather
than frozen into a build. Components apply them only to real-provider controls;
offline fixtures keep their own covered dates. The default analysis range is 720
actual exchange sessions, compatible with the bounded 480/20 backtest. These are
initial controls, not an assertion of data freshness between explicit refreshes.
No credentials are supplied to the browser and no live quote stream is claimed.

## Date selection, coverage and explicit range downloads

Changing browser dates originally only searched materialized bars. The default
480-session lookback also rejected shorter selections without an easy adjustment.
Expose provider-specific stored bounds/count separately from the price payload,
and add a user-triggered range download for the configured real provider. The
download uses the same validated ingestion service, immutable audit snapshots,
fixed provider destination, ten-second provider-request timeout, complete-session
validation, range/body bounds and shared two-job capacity limit. GET routes remain
free of provider I/O. The browser proxy permits only the new fixed coverage/refresh
paths; credentials stay in the backend.

Reject ranges with no exchange session or an observation beyond the conservative
last completed New York session before calling the provider. Stored bounds alone
do not prove every interior session exists. Price reads can display their observed
bars; numerical services continue to reject gaps. Errors never cause cross-feed
or synthetic substitution.

Keep price charts usable when a range cannot support the chosen analytical model.
Offer a smaller lookback as an explicit user choice and display backtest sample
requirements. Do not silently shorten training or retune a financial model to
make a requested date range succeed. Changing inputs clears prior results and
ignores stale browser responses; an aborted browser request does not promise that
an already-running server-side data ingestion was canceled.

The real IEX browser download path was exercised with the host API/proxy context
in this cloud runner (QQQ, 2022-01-03–2022-12-30, 251 observations), followed by
short-range cycle/forecast analysis. Docker Desktop uses direct container provider
access. This runner's API container does not inherit the host's network-secret
proxy context; use a host API when exercising new upstream downloads here.
