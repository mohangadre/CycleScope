# AGENTS.md — Instructions for Coding Agents in CycleScope

## Mission

Implement the project described in [`PROJECT_SPEC.md`](./PROJECT_SPEC.md) as a **working, testable, portfolio-quality full-stack application**. Treat that specification as the product/engineering source of truth. This file defines agent behavior, implementation sequence, quality gates, and non-negotiable safeguards.

**Prioritize demonstrable software engineering over an impressive-looking but untested financial prediction demo.** Financial cycle hypotheses must be tested on held-out data and communicated with appropriate uncertainty.

## On every session

1. Read this file and `PROJECT_SPEC.md`; inspect `README.md`, repo structure, current tests, and git status if available.
2. Identify the **earliest incomplete P0 acceptance criterion** from Section 10 of the spec. Work on that before stretching into P1/P2.
3. Make a concise task plan for nontrivial changes. Prefer vertical slices that actually run end-to-end over disconnected scaffolding.
4. Inspect existing code before adding abstractions or dependencies. Preserve working behavior and existing project conventions.
5. Implement, add/update tests, run the relevant checks, and report what passed, failed, or was not run.
6. Update documentation or the task checklist for changed behavior. Keep progress and known gaps factual.

If the environment lacks external network access, credentials, Docker, or a service, continue with deterministic local fixtures and tests. Explain what is unverified; do not pretend a network-backed or deployed feature works.

## Priority order

**P0 implementation order:**

1. Local setup, backend/analytics packages, provider abstraction, synthetic fixtures, database and prices API.
2. FFT implementation and synthetic-signal tests.
3. Harmonic model, no-lookahead forecasting, walk-forward baseline comparison.
4. Frontend price/cycle/forecast/backtest user flow.
5. Sector relative-strength service and dashboard.
6. CI, docs, reproducible demo, hardening.

**P1 only after P0 works:** wavelets, enhanced evaluation, calibrated forecast intervals, asynchronous jobs/Redis, performance benchmarking, live hosting.

**P2 only after explicit need:** macro regime/HMM models, Chebyshev comparisons, broad universes, strategy simulation, scaling experiments.

Do not implement speculative features or overhaul architecture merely to use more technologies.

## Technology defaults

- Python 3.12+, FastAPI, Pydantic, NumPy/SciPy, pandas, SQLAlchemy, Alembic, PostgreSQL.
- Next.js, TypeScript strict mode, a maintained plotting library such as Plotly.
- pytest for Python, a TypeScript-aware test runner if relevant, and Playwright for essential UI smoke tests.
- Docker Compose for repeatable local setup; GitHub Actions for CI.
- Use Redis/queue infrastructure **only once there is a measured or clear long-running workload need**.
- Prefer stable, maintained versions and pin dependencies/commit lock files using repository standards. Do not add large ML frameworks when SciPy can solve the task.

## Code organization and design rules

- Keep market data adapters (`provider-specific I/O`), domain services (`business logic`), analytics (`numerical transformations`), persistence (`ORM/repos`), HTTP routes (`transport`), and UI (`presentation`) separate.
- Numerical functions should accept arrays/data frames/configuration and return typed data; avoid network calls and database writes inside mathematical algorithms.
- Expose provider-neutral interfaces, typed Pydantic request/response models, deterministic model configs, and explicit units.
- Do not rely on notebooks for production logic. Notebooks may be added as examples/experiments that import the production analytics package.
- Avoid hidden global state, magic numbers, duplicate analytic implementations, broad exception swallowing, and giant utility modules.
- Ensure async web handlers do not directly run unbounded CPU-heavy tasks on an event loop; use bounded execution or background work as appropriate.
- Make ingest/update operations idempotent; create migrations for schema changes and indexes for date/ticker queries.
- Use straightforward components and clear information hierarchy. Always label synthetic data, forecast origin, and actual-versus-projected series.

## Quantitative correctness: hard requirements

### Data integrity

- Never invent stock prices, spectral powers, test results, model significance, confidence levels, or performance benchmarks.
- Offline fixtures must be tagged `synthetic` in the backend and UI. Real endpoints must fail clearly without configured data rather than silently substituting synthetic data.
- Declare price adjustment policy (adjusted vs raw). Do not silently mix series from incompatible providers or adjustment bases.
- Use observed exchange **trading-session dates** and explicitly distinguish trading-session offsets from calendar dates; no naive 365-day or 252-day date arithmetic for exact sessions.
- Validate missing/duplicate bars, finite numeric input, nonpositive prices before log transforms, series length, forecast horizon, and symbol syntax.

### Look-ahead and evaluation

- Any `as_of` forecast must use only bars available by that cutoff, including preprocessing, scaling, detrending, FFT peak selection, model selection, and fitting.
- Never run FFT, scaler fitting, or hyperparameter selection on the entire dataset before train/test splitting.
- Derive predicted turning points **from a forecast made at the training cutoff**, not by labeling a smoothed hindsight chart.
- For realized turning-point evaluation, use a documented event-definition and tolerance; any look-forward needed to confirm historical peaks belongs **only** to evaluation labels, never to contemporaneous inputs.
- Always compare forecasts to a last-observed-price/random-walk baseline at matching cutoffs, symbols, horizons, and targets. Improve baseline coverage later.
- Use expanding/rolling walk-forward folds. Include fold boundaries and cutoff dates in saved results.
- Confidence/prediction interval claims require an actual interval algorithm and empirical coverage evaluation; otherwise call it a heuristic uncertainty band.
- Spectral peak prominence does **not** imply statistical significance. Report `not_tested` until a defensible null test is implemented.
- Account for repeated testing and autocorrelation when implementing significance claims; document caveats.
- Backtest failures or negative out-of-sample findings are acceptable and must be shown accurately.

### Modeling rules

- Implement period conversion as $T=1/f$ using trading sessions, with frequency origin and spectrum normalization specified.
- Exclude DC/zero frequency and reject nonsensical periods or samples with insufficient history; test constant and degenerate inputs.
- For harmonic regression, keep number of harmonics small, select them within each training fold, and use well-defined regularization/selection where appropriate.
- For sector relative strength, consistently use $RS_i=P_i/P_{SPY}$ with matching dates and adjustment policies; document normalization and quadrant thresholds.
- Treat wavelets, HMM regimes, and Chebyshev fitting as incremental optional modules, not proven prediction upgrades.

## Testing expectations

Add tests **in the same change** as new functionality. Minimum cases:

- **Signal recovery:** A noiseless synthetic sine wave of known period returns an appropriate FFT peak (taking sample resolution into account); multi-sinusoid and noisy signal checks.
- **Edge cases:** Constant series, trend-only series, empty/missing dates, irregular sampling, repeated dates, zero/negative prices, invalid horizon, malformed ticker, no provider credentials.
- **No-lookahead:** Append or modify data *after* a forecast cutoff; fitted parameters and cutoff forecasts must remain unchanged.
- **Backtesting:** Ordered folds, no overlap where disallowed, consistent baselines, correct metric denominators, deterministic seed handling.
- **API:** Validations, error payloads/status codes, correct units, serialization, data provenance flags, readiness.
- **Persistence:** Idempotent ingestion, unique keys, migrations/round-trip for experiment configs/results.
- **UI:** Ticker entry, loading state, empty/error state, actual-versus-forecast labeling, displayed method and uncertainty caveats.

CI must run **without private API keys or paid services**. Use small, deterministic fixtures and documented database test setup. Don't weaken/remove failing tests to force a green build.

## Security and operations

- Never commit credentials, tokens, private keys, or `.env` files. Commit `.env.example` with placeholders only.
- Treat all external/provider data as untrusted. Validate API inputs and bound lookback intervals, payload sizes, spectrum parameters, job counts, and concurrency.
- Use database parameterization via an ORM or prepared statements. Do not introduce arbitrary-code execution, user-supplied SQL, unsafe deserialization, or unrestricted outbound URLs.
- Add provider request timeouts and user-visible failure handling. When retries are added, bound them and avoid retry storms.
- Avoid logging sensitive environment variables; structure logs around request/job IDs and sanitized failure reasons.
- Do not execute real trades, request brokerage credentials, or add account integrations as part of this project.

## Working with the repository

- Before editing, check which files are already present and whether they contain user changes. Avoid overwriting unrelated work.
- Prefer a series of small, coherent changes. Do not perform destructive cleanup, reset, rebase, or force push unless explicitly requested.
- If there is no application code, scaffold just enough to complete the current milestone. If an equivalent framework is already configured, adapt rather than replace it.
- Keep API names/schemas, DB migrations, example payloads, frontend types, and docs in sync.
- Add dependencies only when required; explain significant dependencies or architecture choices briefly in `docs/DECISIONS.md`.
- Update `README.md` with exact run/test commands verified in the current environment. Never write a command as "tested" unless it was run.
- If a tool or service cannot run, provide a reproducible fallback and report the limitation in the final summary.
- Avoid generated or vendored dependency directories in git. Use `.gitignore` thoughtfully.

## Definition of done for a feature

A task is complete only when:

1. The code runs for its supported inputs and handles expected errors.
2. Relevant unit/integration/UI tests have been added or updated.
3. Applicable formatting, lint, type-check, and tests have been executed and results noted.
4. API/UI behavior is documented, including return units, assumptions, and limitations.
5. Any finance-related output is clearly sourced or labeled synthetic; no untested performance claims are made.
6. The work supports a concrete acceptance criterion or an explicitly requested enhancement.

For each completed task, summarize **what changed**, **what was verified**, **what is still blocked/missing**, and **which acceptance criterion to tackle next**. Never claim P0 or a phase is complete if any required acceptance criterion remains unmet.

## First execution instruction for a new Codex agent

> Read `AGENTS.md` and `PROJECT_SPEC.md` thoroughly. Inspect the repository before making changes. Implement **Week 1 / P0** first: project skeleton as needed, a deterministic offline market-data provider, a provider-neutral data model, PostgreSQL persistence/migrations, FastAPI health/symbols/prices endpoints, and automated tests. Keep the implementation minimal, document exact setup commands, and run checks. Do **not** jump ahead to the frontend, forecasting, Redis, or deployment until the first milestone is working. If repository code already covers part of Week 1, extend it instead of rebuilding it.

---

**Always optimize for trustworthy, reproducible engineering work.** An honest model that fails to outperform a baseline is preferable to fabricated profitability or a visually convincing but invalid backtest.
