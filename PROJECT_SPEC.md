# CycleScope — Product & Engineering Specification

**Status:** Build specification (proposed, not an implementation report)  
**Project type:** Portfolio-quality, full-stack financial time-series analytics platform  
**Primary audience:** New-graduate software engineering recruiters and interviewers  
**Companion instructions:** [`AGENTS.md`](./AGENTS.md)

## 1. Executive summary

Build **CycleScope**, an end-to-end application that lets users investigate recurring patterns in equities and sector ETFs, test whether those patterns persist, and evaluate whether they improve **out-of-sample** forecasts of future turning points. The application also compares sector-relative strength to visualize potential sector rotations.

The deliverable is **software engineering infrastructure with mathematically rigorous analytics**, not a claim that stock prices can be reliably predicted. The project should demonstrate clean application architecture, numerical programming, reliable data ingestion, API design, data persistence, testing, performance measurement, observability, and deployment.

### User goals

1. **Find cycles:** Detect candidate periodicities, report their lengths in trading sessions, and indicate whether they are stable or statistically distinguishable from noise.
2. **Forecast turning points:** Generate harmonic-regression forecasts, estimate possible future peak/trough windows, quantify uncertainty, and compare forecasts against baselines using walk-forward tests.
3. **Analyze sector rotation:** Compute benchmark-relative strength and momentum across major US sectors; show which sectors are leading, improving, weakening, or lagging.
4. **Inspect the evidence:** Understand data provenance, model assumptions, evaluation windows, diagnostics, and limitations before interpreting a forecast.

### Definition of success

A reviewer can clone the repository, bring up the application with documented commands, analyze several tickers with both sample and configured market data, view market-cycle results and backtests in the UI, run the automated test suite, inspect an API specification, and reproduce at least one published experiment using only versioned code and recorded settings.

No results should be invented to meet this definition.

## 2. Scope and priorities

### P0 — Minimum viable product (build first)

- Responsive web application with ticker selection for `SPY`, `QQQ`, `NVDA`, and `MU` (and additional symbols when available).
- Historical daily OHLCV retrieval through a **swappable data-provider adapter**, with checked-in synthetic fixtures enabling local/offline development.
- Clean, validated storage of daily adjusted observations and associated ingestion metadata.
- Cycle analysis: detrending/returns preprocessing, FFT-based periodogram, candidate frequency detection, and a chart of spectral power versus period.
- Harmonic-regression forecast with a clear historical/forecast cutoff, simple uncertainty display, and candidate peak/trough windows.
- Expanding-window or rolling-window **walk-forward backtesting**, including a no-change/random-walk baseline.
- Sector relative strength against `SPY` for a documented set of sector ETFs; simple leader/laggard visualization.
- FastAPI backend, Next.js/TypeScript frontend, PostgreSQL persistence, automated numerical/API tests, Docker Compose setup, and meaningful README.

### P1 — Portfolio-strength enhancements (after P0 works)

- Rolling-window cycle analysis and continuous wavelet transform or discrete wavelet-based stability view.
- More baselines: trailing-average extrapolation and autoregressive model.
- Additional backtest metrics: turning-point precision/recall, timing error, interval coverage, and statistical tests against autocorrelated null models.
- Reproducible experiment IDs that tie a forecast to as-of date, dataset snapshot, feature settings, and fitted parameters.
- Scheduled ingestion, job status endpoints, Redis caching, background workers, retries, rate-limit handling, and structured telemetry.
- CI pipeline with lint, type check, tests, and reproducible build; hosted demo if suitable infrastructure/credentials exist.

### P2 — Optional research extensions (not prerequisites for completion)

- Macroeconomic indicators sourced from FRED, aligned by **release/availability date** rather than revised present-day values.
- Hidden Markov Models (HMMs) for bull/bear/sideways or macro regime classification.
- Point-in-time sector membership and broader universes; wavelet coherence, multivariate sector relationships, and simulation-based significance testing.
- Optional strategy simulation including transaction costs; **not** automated brokerage execution.
- Performance profiling, batch analysis for hundreds of tickers, and caching/queue throughput benchmarks.
- Chebyshev polynomial approximation as a **comparison/visualization**, never presented as inherently periodic or a reliable extrapolator.

### Explicit non-goals

- Guaranteed stock-price forecasts, promises of trading profit, or investment recommendations.
- Live order execution, exchange connectivity for trading, or personal financial account access.
- Real-time tick-level streaming, options valuation, or production-grade low-latency trading.
- Premature microservices, Kubernetes, elaborate cloud infrastructure, or paid data dependencies required for local development.
- Decorative metrics, fabricated backtest performance, or dashboard numbers without a verifiable source.

## 3. Core user experience

### A. Stock Cycle Explorer

- Enter/select ticker and date range; select close/log close/log returns where meaningful.
- Chart **observed** historical prices and annotate the fit period and forecast start.
- Present candidate cycle periods in **trading sessions**, spectral strength, and whether evidence survives chosen noise/significance checks.
- Display FFT power spectrum, preprocessing choices, and window/threshold settings.
- Show rolling or wavelet stability analysis once P1 is implemented.
- Explain that spectral peaks indicate candidate historical cycles, **not** proved future periodicity.

### B. Turning-Point Forecast

- Show projected harmonic curve from the forecast origin onward with a distinct style from observed history.
- Highlight local maxima/minima of the **forecast** and report them as estimated windows, not specific guaranteed dates.
- Show interval method and horizon explicitly; if uncertainty has not been calibrated, label the projection as exploratory and don't call the interval a calibrated confidence level.
- Present a backtest panel comparing model versus baselines using matching target/horizon definitions.
- For any reported prediction, allow users to inspect what was known at the prediction's **as-of timestamp**.

### C. Sector Rotation Dashboard

- Compare `XLK`, `XLF`, `XLE`, `XLI`, `XLU`, `XLV`, `XLY`, and `XLP` with `SPY`.
- Plot benchmark-normalized relative strength, momentum, and change in relative strength for each sector.
- Classify leading/improving/weakening/lagging using explicitly documented quadrant thresholds; make lookback adjustable.
- Show *observed* relative performance separately from optional projected rotation/regime estimates.
- Explain that sector labels are heuristic and not an economic law.

### D. Experiment / methodology view

- Record model configuration, frequency range, training cutoff, test intervals, source metadata, software version, baseline choices, and evaluation metrics.
- Show the same experiment results when reloaded with its persistent identifier.
- Label all artificial examples **SYNTHETIC DATA** and all real measurements by source/as-of date.

## 4. Technology and system architecture

| Component | Default choice | Responsibility |
|---|---|---|
| Frontend | Next.js + TypeScript, Plotly or equivalent | Responsive dashboard, forms, charting, async job status |
| API | Python 3.12+, FastAPI + Pydantic | Request validation, orchestration, HTTP error handling, OpenAPI |
| Analytics | NumPy, SciPy, pandas, scikit-learn | FFT, peaks, regression, baseline models, metrics |
| Wavelets (P1) | PyWavelets | Localized time-frequency analysis |
| Time-series baselines (P1) | statsmodels | AR/autoregressive baseline |
| Storage | PostgreSQL + SQLAlchemy + Alembic | Adjusted bars, ingestion runs, model runs, results |
| Optional cache/queue (P1) | Redis + Celery or RQ | Deduplication and background jobs |
| Packaging/CI | Docker Compose, GitHub Actions | Reproducible local environment and automated checks |
| Deployment (P1) | Practical managed hosting / AWS | Public read-only demo with secret management |

### High-level request flow

```text
Next.js dashboard
     |
     | HTTPS / JSON
     v
FastAPI (validation, analytics endpoints)
     |                      |
     v                      v
PostgreSQL            Analytics engine
(data + provenance)   (FFT / harmonic / backtest / sectors)
     ^                      |
     |                      v
Market data adapter    Experiment artifacts + metrics
(offline fixture or    (PostgreSQL; optional async job)
 configured provider)
```

**Architectural rules:** Separate I/O from numerical methods; keep analytics as testable pure functions when possible; use typed request/response models; never make the UI depend directly on provider-specific response shapes. Start with one backend application, not distributed microservices.

### Market data providers

- Implement `MarketDataProvider` protocol/interface with `get_daily_bars(symbol, start, end)` and named implementations for offline fixtures and one documented market-data API (e.g., Alpaca's historical stock-bars API).
- FRED is an optional P2 macro source: https://fred.stlouisfed.org/docs/api/fred/ .
- Respect provider licensing, authentication, rate limits, symbol coverage, and adjustment semantics. If credentials are missing, return a clear error or use **explicitly labeled** synthetic fixtures; **never** silently substitute fictional market results.
- Store original source, request time, observation date, adjustment policy, currency, provider identifier, and data version where feasible.
- Establish one canonical OHLCV schema with unique `(symbol, session_date, adjustment_basis, provider)` (or a documented equivalent), idempotent upserts, and UTC timestamps. Dates for daily bars are **exchange session dates**; do not assume all calendar dates are trading sessions.
- Use adjusted close for cross-date returns and ratios where appropriate. Never mix adjusted and raw series in the same computation without explicit handling.
- Handle holidays, missing sessions, duplicate bars, provider outages, API pagination, insufficient history, invalid symbols, and stale data.

## 5. Mathematical specification

All descriptions below are modeling hypotheses to **test**, not predictive facts.

### 5.1 FFT-based candidate cycle detection

For a uniformly sampled series $x_t$ observed over $N$ trading sessions, apply a specified transform (e.g., log price detrended with training-only methods, or log returns):

$$X_k=\sum_{t=0}^{N-1}x_t e^{-2\pi i kt/N},\quad f_k=\frac{k}{N},\quad T_k=\frac{1}{f_k}.$$

- Center the input; use an explicitly documented detrending method, optionally taper with a Hann window, and exclude the zero-frequency component.
- Use `numpy.fft.rfft` / `scipy.signal.periodogram` and make spectrum normalization explicit.
- Detect peaks using `scipy.signal.find_peaks` with configurable prominence/spacing; report at most a small number of dominant candidates.
- Return $T_k$ in **trading sessions**, not calendar days; note that finite history creates a frequency-resolution limit.
- Reject/flag periods that cannot plausibly be estimated given the training window (e.g., periods too short for the sampling rate or too long for multiple observed repetitions). Document chosen bounds; avoid hard-coded unmotivated filters.
- Test with synthetic sine waves at known periods (e.g., 40, 120 sessions), mixed harmonics, noisy data, constant series, trending series, and random-walk-like signals.
- Avoid claiming statistical significance merely because a peak ranks highest. In P1, compare peaks to an autocorrelation-aware null using a documented resampling/simulation procedure, and address multiple-frequency scanning.

### 5.2 Time-localized / wavelet analysis (P1)

Use a continuous wavelet transform (or well-documented alternative) to inspect whether candidate cycle frequencies persist or change through history:

$$W(a,b)=\frac{1}{\sqrt{|a|}}\int_{-\infty}^{\infty}x(t)\psi^*\left(\frac{t-b}{a}\right)dt.$$

Report dominant periods by date/window. Document mother wavelet, sampling frequency, scale-to-period mapping, boundary effects, cone-of-influence/edge handling if relevant, and numerical choices. A wavelet heatmap should not be labeled evidence of forecast accuracy without out-of-sample validation.

### 5.3 Harmonic regression and turning points

Fit harmonic terms to **training-only** observations at candidate frequencies chosen within that training fold:

$$\hat y(t)=\beta_0+\beta_1 t+\sum_{k=1}^{K}\left[a_k\cos(2\pi t/T_k)+b_k\sin(2\pi t/T_k)\right].$$

Here $y(t)$ may be log adjusted price (with a training-only trend component) or log returns; compare both if feasible. Use least squares or ridge-regularized regression. Limit $K$, use model selection without test leakage, and report fit assumptions.

- Extrapolate the fitted model only from the fold's cutoff, not from the end of the full dataset.
- Identify predicted turning points from the future projection using local-extrema logic (`find_peaks` for peaks and inverted series for troughs), with configurable minimum separation and forecast horizon.
- Convert forecast session offsets to expected exchange session dates using a trading calendar; distinguish offsets from calendar days.
- Represent a predicted turning point as a **window** based on explicit tolerance/calibration logic. A naive ±N-day window must be labeled heuristic.
- Produce uncertainty with a documented, leakage-free method (e.g., rolling out-of-sample forecast residual quantiles or bootstrap on training residuals); do not conflate parameter uncertainty and future predictive uncertainty.
- Persist the fitted periods, coefficients, train range, as-of date, horizon, data snapshot/source, and model version.

### 5.4 Sector relative strength and momentum

For sector ETF $i$ benchmarked to `SPY`:

$$RS_i(t)=\frac{P_i(t)}{P_{SPY}(t)}.$$

Normalize relative strength to a chosen reference date (e.g., $100 \times RS_i(t)/RS_i(t_0)$) for comparable charts. Define momentum as a backward-looking change in log relative strength, optionally smoothed:

$$M_i(t;L)=\log RS_i(t)-\log RS_i(t-L).$$

Define and document a four-quadrant labeling rule using levels and changes in smoothed relative strength. Use the same date basis and adjustment policy for all symbols. Sector labels are descriptive, not predicted winners.

### 5.5 Optional polynomial comparison

Chebyshev polynomials follow

$$T_{n+1}(x)=2xT_n(x)-T_{n-1}(x),\qquad P(t)\approx\sum_{k=0}^{N}c_kT_k(\tilde t).$$

Use as an optional **in-sample curve approximation comparison** and document poor extrapolation characteristics. Do not present Chebyshev polynomials as a naturally cyclic alternative to Fourier harmonics.

## 6. Evaluation and anti-leakage contract

### Walk-forward evaluation

- Create ordered expanding or rolling training windows followed by nonoverlapping or clearly documented evaluation windows.
- For each fold, calculate detrending, scaling, FFT cycle selection, feature engineering, hyperparameter tuning, and fitting **using only training observations**. Never compute a full-dataset spectrum before splitting.
- Compare identical symbols, cutoff dates, target definitions, and horizons across models.
- Baseline 1 (P0): random walk / last observed log-price carried forward. Baseline 2 (P1): moving-average extrapolation. Baseline 3 (P1): simple autoregressive model.
- Produce evaluation artifacts with enough metadata to rerun the identical experiment.

### Metrics

| Metric | Definition / requirement |
|---|---|
| MAE, RMSE | Specify target (log price, price, or return), units, horizon; compare baseline |
| Directional accuracy | Share of future return signs correctly predicted over a specified horizon |
| Turning-point precision/recall | Define a peak/trough detection rule on realized series, forecast horizon, and match tolerance; one-to-one matching only |
| Turning-point timing error | Trading sessions between matched predicted and realized turning points |
| Interval coverage | Empirical proportion of outcomes inside prediction interval, plus nominal coverage level |
| Latency and throughput | Report benchmark dataset, hardware, warm/cold cache, request counts, p50/p95 |

**Important constraints:** Peak labels on the realized series may require *future* observations to confirm a local maximum; use such labels for retrospective evaluation only. Don't use them for training features before they become observable. Avoid survivorship bias in evolving universes and vintage/revision leakage if macro series are added.

### Results reporting

- Do not promise positive alpha or profitable timing.
- Clearly distinguish in-sample curve fit from out-of-sample forecasting accuracy.
- Publish negative results if present; an honest failure to beat the baseline is a valid research finding.
- Synthetic demonstration charts must be distinctly and continuously labeled as examples.

## 7. API contract (proposed v1)

Root: `/api/v1`. Use JSON, OpenAPI-generated documentation, Pydantic validation, stable error shapes, pagination for long datasets, and timezone-aware ISO-8601 timestamps. Prefer a consistent envelope or documented response schemas rather than mixing formats.

| Route | Method | Purpose | Priority |
|---|---|---|---|
| `/health` | GET | Readiness/liveness diagnostics (no secrets) | P0 |
| `/api/v1/symbols` | GET | Supported tickers and descriptive metadata | P0 |
| `/api/v1/prices/{ticker}` | GET | Historical OHLCV / adjusted prices (`start`, `end`) | P0 |
| `/api/v1/cycles/{ticker}` | GET | FFT peaks and analysis metadata (`lookback`, config) | P0 |
| `/api/v1/forecasts/{ticker}` | POST | Forecast for a specified `as_of`, horizon, and model config | P0 |
| `/api/v1/backtests` | POST | Launch/run reproducible evaluation; synchronous for small P0 tests | P0 |
| `/api/v1/backtests/{run_id}` | GET | Results, baselines, metrics, fold metadata | P0 |
| `/api/v1/sectors/rotation` | GET | Benchmark-relative sector strength/momentum | P0 |
| `/api/v1/jobs/{job_id}` | GET | Job state, failure reason, result reference | P1 |

Example *shape only* (all values illustrative):

```json
{
  "ticker": "MU",
  "analysis_method": "fft",
  "input": "detrended_log_adjusted_close",
  "as_of": "2026-10-16",
  "sample_count": 1250,
  "period_unit": "trading_sessions",
  "cycles": [
    {
      "period_sessions": 120.0,
      "spectral_power": 0.91,
      "significance_status": "not_tested"
    }
  ],
  "data_kind": "synthetic_example"
}
```

**Notes:** Never return `significant: true` without an implemented significance method and stored criterion. Each response should identify real-versus-synthetic data. HTTP errors should differentiate bad input (400/422), unknown symbol (404), unavailable upstream provider (502/503), insufficient data (422 with explanation), and internal faults (500 without leaking secrets).

## 8. Data model and reproducibility

Initial logical entities (names may vary after migrations):

- **Instrument:** canonical symbol, display name, asset class, exchange, currency, active/status metadata.
- **DailyBar:** instrument, exchange session date, OHLCV, adjusted price fields, adjustment basis, provider, ingestion timestamp.
- **DataSnapshot / IngestionRun:** source, request parameters, coverage interval, fetched time, provenance/version/hash, warnings/errors.
- **AnalysisRun:** UUID, ticker or universe, analysis configuration, as-of cutoff, input snapshot, library/git revision, created timestamp, status.
- **CycleEstimate:** analysis run, candidate period, frequency, power, rank, significance method/status, stability measures if available.
- **ForecastPoint:** analysis run, forecast session/date, value, bounds, predicted/extremum flags.
- **BacktestFold / BacktestMetric:** run, train/test boundaries, model name, metric name/value/units, evaluation configuration.
- **SectorObservation:** session date, sector symbol, SPY benchmark, normalized RS, relative momentum, labeled state, model/rule version.

Use schema migrations, indexes for `(symbol, session_date)`, idempotent ingestion, and explicit data-retention choices. Replaying a stored experiment should reuse the recorded snapshot/configuration or explain why exact replay is unavailable; never quietly rerun on revised data and call it identical.

## 9. Quality, security, and operational requirements

### Automated testing

- **Unit:** synthetic 40/120-session sinusoids recovered within justified tolerance; trend removal; boundary cases; peak indexing; four-quadrant sector logic; metrics.
- **Property/invariant:** deterministic results on identical inputs; no NaN/Infinity in serialized responses; strictly increasing observation dates; consistent periods and units.
- **Leakage tests:** changing observations *after* a training cutoff must not change fitted parameters or predictions for that cutoff.
- **Integration:** ingest fixture -> database -> API -> analysis/backtest; idempotent repeated ingestion.
- **Frontend/E2E:** enter ticker -> display prices and cycle periods -> run forecast -> inspect backtest; clear error handling and loading states.
- **Performance (P1):** benchmark cold/warm analysis and compare naive DFT versus FFT with recorded settings.

### Engineering practices

- Formatter/linter, Python type checking where practical, TypeScript strict mode, checked-in dependency lock files, `.env.example`, and documented scripts.
- Secrets stay in environment/secret managers, never in source or example responses.
- Input validation for ticker, ranges, horizon, frequency bounds, payload sizes; pagination and safe query patterns.
- Service should degrade gracefully on empty provider data or provider errors; use timeouts and bounded retries (P1).
- Structured logs with request IDs and task IDs; never log API keys or raw credentials.
- CI must test against fixtures without requiring market API keys. Document any integration tests requiring optional credentials.
- Responsive layout with legible axes, accessible controls, and a textual method/limitations section; charts are not the only way to see key results.

### Performance targets (aspirational; measure, don't invent)

- Typical cached small-data read targets ~300 ms server-side p95 on documented demo hardware.
- Initial single-ticker FFT/cycle analysis target under ~2 seconds for five years of daily observations on developer hardware.
- Long backtests should use background jobs in P1 to avoid HTTP timeouts.
- Publish measured throughput, cache hit rate, and execution environment when reporting performance.

## 10. Milestones and acceptance criteria

### Week 1 — Data and backend

- [ ] Repository skeleton, development setup, Docker Compose, environment template.
- [ ] Provider interface, offline fixtures, one configurable API adapter, robust ingestion.
- [ ] PostgreSQL schema + migrations, ticker/prices/health endpoints, OpenAPI documentation.
- [ ] Unit/integration tests for providers, parsing, storage, and error paths.

**Acceptance:** A fresh checkout can load fixtures into PostgreSQL and fetch price history from FastAPI with no external credentials.

### Week 2 — Numerical engine and backtesting

- [ ] FFT preprocessing, periodogram, candidate periods with validation.
- [ ] Harmonic-regression training and strictly future-only turning-point forecasts.
- [ ] Walk-forward evaluator, random-walk baseline, MAE/RMSE/directional accuracy.
- [ ] Synthetic frequency recovery, no-lookahead, and reproducibility tests.

**Acceptance:** API can return documented cycle analyses and backtest reports; synthetic known-frequency tests pass; forecasts cannot use future data.

### Week 3 — Dashboard and user workflow

- [ ] Ticker/date range selection, historical price chart, cycle spectrum and method details.
- [ ] Forecast chart with cutoff and uncertainty caveat; backtest comparison.
- [ ] Useful loading, empty, invalid ticker, and upstream error states.
- [ ] Frontend smoke/E2E test of core journey.

**Acceptance:** A reviewer can complete the P0 single-ticker analysis through the web UI without manually calling APIs.

### Week 4 — Sector analysis and polish

- [ ] Sector-relative strength endpoint and dashboard.
- [ ] Robust tests, CI, documentation, architecture diagram, reproducible demo experiment.
- [ ] Deployment/read-only live demo if feasible; otherwise fully functional local demo.
- [ ] Measured performance notes, documented limitations, screenshots.

**Acceptance:** MVP works end-to-end, all required tests pass, README includes one-command-ish setup, and claims are supported by actual outputs.

### Stretch sequence

1. Wavelets and rolling cycle stability.
2. Better turning-point labeling, null-model significance, and calibrated intervals.
3. Background jobs, caching, and measured performance improvements.
4. Macro/HMM regime research (vintage-safe) and larger-universe processing.

## 11. Recommended repository layout

```text
cyclescope/
├── AGENTS.md
├── PROJECT_SPEC.md
├── README.md
├── frontend/
│   ├── app/
│   ├── components/
│   │   ├── PriceChart.tsx
│   │   ├── CycleSpectrum.tsx
│   │   └── SectorDashboard.tsx
│   └── package.json
├── backend/
│   ├── api/
│   │   ├── prices.py
│   │   ├── cycles.py
│   │   ├── forecasts.py
│   │   └── sectors.py
│   ├── services/
│   │   ├── market_data.py
│   │   └── job_manager.py
│   ├── models/
│   │   └── schemas.py
│   └── main.py
├── analytics/
│   ├── fourier.py
│   ├── wavelets.py
│   ├── harmonic.py
│   ├── sector_rotation.py
│   └── backtesting.py
├── tests/
│   ├── fixtures/
│   ├── unit/
│   └── integration/
├── alembic/
├── .github/workflows/
├── docker-compose.yml
└── .env.example
```

Treat this as a **logical layout**. Prefer a coherent importable Python package over fragile path hacks, and adapt to existing repository conventions if present. Importing `analytics` must not run requests or mutate storage.

## 12. Resume-worthy evidence and documentation

Design and measure the following while building:

- Number of tickers and historical observations successfully ingested (real, countable values).
- Number of backtest folds and reproduced experiments.
- Model-versus-baseline performance on held-out data, including failures.
- FFT versus naive DFT timing with exact input sizes, if optimized.
- p50/p95 API latency on measured environment before/after cache introduction.
- Test suite scope, CI pipeline, and deployed demo URL (only once actually deployed).

Potential résumé wording **only after the claims are verifiably true**:

> **CycleScope — Full-Stack Financial Time-Series Analytics Platform** | Python, FastAPI, React, TypeScript, PostgreSQL, Docker  
> - Engineered a market analytics platform integrating historical stock ingestion, REST APIs, relational storage, and interactive cycle/sector visualizations across **[measured X]** equities and ETFs.  
> - Implemented FFT-based cycle detection and harmonic-regression forecasting; evaluated turning-point signals using leakage-free walk-forward backtests against statistical baselines.  
> - Built tested analytics services and repeatable deployments; reduced **[measured operation]** latency by **[measured X]%** through **[implemented optimization]**.

Never present placeholders as actual achievements.

## 13. Documentation and deliverables

Deliver a public-ready repo containing:

- `README.md`: overview, demo images, architecture, prerequisites, commands, API examples, limitations, link to demo if deployed.
- `PROJECT_SPEC.md` and `AGENTS.md`.
- Working source code and tracked database migrations.
- Runnable synthetic fixtures and one deterministic demonstration experiment.
- Backend unit/integration tests and a frontend smoke test.
- `docker-compose.yml`, `.env.example`, and CI workflow.
- API docs accessible through FastAPI's generated OpenAPI UI.
- A short `docs/METHODOLOGY.md` explaining transforms, detected cycle interpretation, leakage controls, metric definitions, and evaluation results.
- `docs/DECISIONS.md` (or ADRs) for meaningful architecture tradeoffs.

## 14. Reference links

- Historical bar provider example: https://docs.alpaca.markets/us/reference/stockbars
- FRED API documentation: https://fred.stlouisfed.org/docs/api/fred/
- Numerical primitives: https://numpy.org/doc/stable/reference/routines.fft.html and https://docs.scipy.org/doc/scipy/reference/signal.html
- Wavelets: https://pywavelets.readthedocs.io/
- API framework: https://fastapi.tiangolo.com/

These are implementation references, not evidence that the forecast methods will work in financial markets.

---

**Guiding principle:** The project's most compelling achievement is a reliable, measurable and scientifically honest system for testing cyclic hypotheses—not a dashboard that claims to predict markets without evidence.
